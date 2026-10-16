import logging
import os
import uuid
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import db as db_module
from app.auth import get_current_user
from app.core.config import settings
from app.repositories.document_chunk_repository import (
    DocumentChunkRepository,
    DocumentNotFoundError,
    DocumentNotReadyError,
)
from app.schemas.db_health import DBHealthResponse
from app.schemas.document_processing import DocumentProcessingResponse
from app.schemas.document_upload import DocumentUploadResponse, ExtractionSummary
from app.schemas.health import HealthResponse
from app.schemas.retrieval import (
    DocumentAnswerRequest,
    DocumentAnswerResponse,
    DocumentSearchRequest,
    DocumentSearchResponse,
)
from app.services.answer.client import AnswerClientError, OpenRouterAnswerClient
from app.services.answer.service import AnswerService
from app.services.chunking import ChunkingConfig, StructureAwareChunker
from app.services.document_parser import parse_docx, parse_pdf
from app.services.document_processing_service import (
    DocumentProcessingError,
    DocumentProcessingService,
)
from app.services.embeddings.openrouter_provider import EmbeddingProviderError
from app.services.embeddings.openrouter_provider import OpenRouterEmbeddingProvider
from app.services.retrieval.service import RetrievalService
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


def get_document_processing_service() -> DocumentProcessingService:
    if settings.embedding_provider != "openrouter":
        raise HTTPException(
            status_code=503, detail="Embedding provider is not configured."
        )
    if not settings.openrouter_api_key:
        raise HTTPException(
            status_code=503, detail="Embedding provider is not configured."
        )
    if settings.embedding_dimensions != 1536:
        raise HTTPException(
            status_code=503,
            detail="Configured embedding dimension does not match the database schema.",
        )

    return DocumentProcessingService(
        repository=DocumentChunkRepository(),
        storage=SupabaseStorageService(),
        chunker=StructureAwareChunker(
            ChunkingConfig(
                target_tokens=settings.chunk_target_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
                max_tokens=settings.chunk_max_tokens,
                tokenizer_encoding=settings.chunk_tokenizer_encoding,
            )
        ),
        embedding_provider=OpenRouterEmbeddingProvider(
            api_key=settings.openrouter_api_key,
            model_id=settings.embedding_model,
            dimension=settings.embedding_dimensions,
            batch_size=settings.embedding_batch_size,
            timeout_seconds=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
        ),
    )


def get_embedding_provider() -> OpenRouterEmbeddingProvider:
    """FastAPI dependency: builds and validates the embedding provider from settings.

    Shared by the /search and /answer endpoints so provider construction is
    never duplicated and config validation happens in one place.
    """
    if not settings.openrouter_api_key:
        raise HTTPException(
            status_code=503, detail="Embedding provider is not configured."
        )
    if settings.embedding_dimensions != 1536:
        raise HTTPException(
            status_code=503,
            detail="Configured embedding dimension does not match the database schema.",
        )
    return OpenRouterEmbeddingProvider(
        api_key=settings.openrouter_api_key,
        model_id=settings.embedding_model,
        dimension=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
        timeout_seconds=settings.embedding_timeout_seconds,
        max_retries=settings.embedding_max_retries,
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
    file: Annotated[UploadFile, File()],
    user: Annotated[dict, Depends(get_current_user)],
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


@app.post(
    f"{settings.api_v1_prefix}/documents/{{document_id}}/process",
    response_model=DocumentProcessingResponse,
)
def process_document(
    document_id: UUID,
    user: Annotated[dict, Depends(get_current_user)],
    processor: Annotated[
        DocumentProcessingService, Depends(get_document_processing_service)
    ],
) -> DocumentProcessingResponse:
    owner_user_id = str(user.get("sub") or user.get("id") or "")
    if not owner_user_id:
        raise HTTPException(status_code=401, detail="Invalid authenticated user.")

    try:
        return processor.process_document(str(document_id), owner_user_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except DocumentProcessingError as exc:
        raise HTTPException(
            status_code=500,
            detail="Document processing failed. Check server configuration and retry.",
        ) from exc


@app.post(
    f"{settings.api_v1_prefix}/documents/{{document_id}}/search",
    response_model=DocumentSearchResponse,
)
def search_document_chunks(
    document_id: UUID,
    request: DocumentSearchRequest,
    user: Annotated[dict, Depends(get_current_user)],
    repository: Annotated[DocumentChunkRepository, Depends()],
    embedding_provider: Annotated[
        OpenRouterEmbeddingProvider, Depends(get_embedding_provider)
    ],
) -> DocumentSearchResponse:
    owner_user_id = str(user.get("sub") or user.get("id") or "")
    if not owner_user_id:
        raise HTTPException(status_code=401, detail="Invalid authenticated user.")

    # Ensure the request document_id matches the path parameter
    if str(document_id) != request.document_id:
        raise HTTPException(
            status_code=400,
            detail="Document ID in path does not match document ID in request body",
        )

    # Initialize retrieval service
    retrieval_service = RetrievalService(repository, embedding_provider)

    try:
        results = retrieval_service.search(request, owner_user_id)
        return DocumentSearchResponse(
            document_id=request.document_id,
            query=request.query,
            mode=request.mode,
            results=results,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except DocumentNotReadyError as exc:
        raise HTTPException(
            status_code=400, detail="Document is not ready for retrieval."
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=503, detail="Embedding provider unavailable."
        ) from exc



def get_answer_client() -> OpenRouterAnswerClient:
    """FastAPI dependency that builds the answer-generation client."""
    if not settings.answer_api_key:
        raise HTTPException(
            status_code=503,
            detail="Answer generation is not configured. Set ANSWER_API_KEY.",
        )
    return OpenRouterAnswerClient(
        api_key=settings.answer_api_key,
        model=settings.answer_model,
        max_tokens=settings.answer_max_tokens,
    )


@app.post(
    f"{settings.api_v1_prefix}/documents/{{document_id}}/answer",
    response_model=DocumentAnswerResponse,
)
def answer_document_question(
    document_id: UUID,
    request: DocumentAnswerRequest,
    user: Annotated[dict, Depends(get_current_user)],
    repository: Annotated[DocumentChunkRepository, Depends()],
    embedding_provider: Annotated[
        OpenRouterEmbeddingProvider, Depends(get_embedding_provider)
    ],
    answer_client: Annotated[OpenRouterAnswerClient, Depends(get_answer_client)],
) -> DocumentAnswerResponse:
    owner_user_id = str(user.get("sub") or user.get("id") or "")
    if not owner_user_id:
        raise HTTPException(status_code=401, detail="Invalid authenticated user.")

    # Step 1: retrieve evidence chunks
    search_request = DocumentSearchRequest(
        document_id=str(document_id),
        query=request.query,
        mode=request.mode,
        top_k=request.top_k,
    )
    retrieval_service = RetrievalService(repository, embedding_provider)

    try:
        chunks = retrieval_service.search(search_request, owner_user_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except DocumentNotReadyError as exc:
        raise HTTPException(
            status_code=400, detail="Document is not ready for retrieval."
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=503, detail="Embedding provider unavailable."
        ) from exc

    # Step 2: generate grounded answer from retrieved evidence
    answer_service = AnswerService(answer_client)
    try:
        result = answer_service.answer(query=request.query, chunks=chunks)
    except AnswerClientError as exc:
        raise HTTPException(
            status_code=503, detail="Answer generation service unavailable."
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DocumentAnswerResponse(
        document_id=str(document_id),
        query=request.query,
        mode=request.mode,
        answer=result.answer,
        cited_chunk_ids=result.cited_chunk_ids,
        invalid_citations=result.invalid_citations,
        retrieved_chunks=chunks,
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
