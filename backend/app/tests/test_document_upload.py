from io import BytesIO
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app


client = TestClient(app)


def test_upload_document_requires_authentication() -> None:
    response = client.post(
        "/api/v1/documents",
        files={
            "file": (
                "notes.pdf",
                b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 401


def test_upload_document_accepts_valid_document() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Uploaded document text")
    buffer = BytesIO()
    doc.save(buffer)
    pdf_bytes = buffer.getvalue()

    app.dependency_overrides.clear()
    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-123"}

    with (
        patch(
            "app.main.persist_document_metadata",
            return_value={"id": "doc-123", "filename": "sample.pdf"},
        ),
        patch(
            "app.main.SupabaseStorageService.upload_document",
            return_value="documents/user-123/doc-123/original.pdf",
        ),
    ):
        response = client.post(
            "/api/v1/documents",
            files={"file": ("sample.pdf", pdf_bytes, "application/pdf")},
        )

    assert response.status_code == 201
    assert response.json()["filename"] == "sample.pdf"
    assert response.json()["storage_path"] == "documents/user-123/doc-123/original.pdf"
    assert response.json()["status"] == "uploaded"

    app.dependency_overrides.clear()
