import logging
import os
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import db as db_module
from app.auth import get_current_user
from app.core.config import settings
from app.schemas.db_health import DBHealthResponse
from app.schemas.document_upload import DocumentUploadResponse, ExtractionSummary
from app.schemas.health import HealthResponse
from app.services.document_parser import parse_docx, parse_pdf
from app.services.storage_service import SupabaseStorageService

logger = logging.getLogger("document_intelligence_api")
MAX_UPLOAD_SIZE_BYTES = 15 * 1024 * 1024


def persist_document_metadata(
    user_id: str,
    filename: str,
    file_type: str,
    storage_path: str,
    document_id: str,
) -> dict[str, str]:
    with db_module.db_session() as connection:
        result = connection.execute(
            text(
                """
                INSERT INTO public.documents (id, user_id, filename, file_type, storage_path, status)
                VALUES (:id, :user_id, :filename, :file_type, :storage_path, :status)
                RETURNING id, filename, file_type, storage_path, status
                """
            ),
            {
                "id": document_id,
                "user_id": user_id,
                "filename": filename,
                "file_type": file_type,
                "storage_path": storage_path,
                "status": "uploaded",
            },
        )
        row = result.mappings().first()
        if row is None:
            raise RuntimeError("Failed to persist document metadata.")
        return {
            "id": str(row["id"]),
            "filename": row["filename"],
            "file_type": row["file_type"],
            "storage_path": row["storage_path"],
            "status": row["status"],
        }


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(f"{settings.api_v1_prefix}/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="document-intelligence-api")


@app.get(f"{settings.api_v1_prefix}/db-health", response_model=DBHealthResponse)
def db_health() -> DBHealthResponse:
    if not db_module.is_database_available():
        raise HTTPException(status_code=503, detail="Database unavailable")
    return DBHealthResponse(status="ok", database="connected")


@app.post(
    f"{settings.api_v1_prefix}/documents",
    response_model=DocumentUploadResponse,
    status_code=201,
)
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> DocumentUploadResponse:
    filename = os.path.basename(file.filename or "document")
    if not filename:
        raise HTTPException(status_code=400, detail="A filename is required.")

    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in {"pdf", "docx"}:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload a PDF or DOCX document.",
        )

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="The uploaded file exceeds the supported 15 MB maximum size.",
        )

    try:
        extraction = (
            parse_pdf(file_bytes, filename)
            if suffix == "pdf"
            else parse_docx(file_bytes, filename)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    user_identifier = str(user.get("sub") or user.get("id") or "anonymous")
    document_id = str(uuid.uuid4())
    storage_service = SupabaseStorageService()
    storage_path = ""
    try:
        storage_path = storage_service.upload_document(
            user_identifier,
            document_id,
            filename,
            file_bytes,
            suffix,
        )
        metadata = persist_document_metadata(
            user_identifier,
            filename,
            suffix,
            storage_path,
            document_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (
        Exception
    ) as exc:  # pragma: no cover - defensive guard for storage/database outages
        if storage_path:
            logger.exception("Document upload failed after storage write", exc_info=exc)
        raise HTTPException(status_code=500, detail="Document upload failed.") from exc

    return DocumentUploadResponse(
        id=metadata.get("id", document_id),
        filename=metadata.get("filename", filename),
        file_type=metadata.get("file_type", suffix),
        status=metadata.get("status", "uploaded"),
        storage_path=metadata.get("storage_path", storage_path),
        extraction=ExtractionSummary(
            block_count=len(extraction.blocks),
            warnings=extraction.warnings,
        ),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    logger.exception("Unhandled server error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
