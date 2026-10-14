from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.core.config import settings
from app.main import app, get_document_processing_service
from app.schemas.document_processing import DocumentProcessingResponse


client = TestClient(app)


def test_document_processing_route_requires_authentication() -> None:
    response = client.post(f"/api/v1/documents/{uuid4()}/process")

    assert response.status_code == 401


def test_document_processing_route_returns_structured_result() -> None:
    document_id = str(uuid4())
    service = MagicMock()
    service.process_document.return_value = DocumentProcessingResponse(
        document_id=document_id,
        status="ready",
        chunk_count=3,
        embedding_model="openai/text-embedding-3-small",
        skipped=False,
    )
    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-123"}
    app.dependency_overrides[get_document_processing_service] = lambda: service

    try:
        response = client.post(f"/api/v1/documents/{document_id}/process")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "document_id": document_id,
        "status": "ready",
        "chunk_count": 3,
        "embedding_model": "openai/text-embedding-3-small",
        "skipped": False,
    }
    service.process_document.assert_called_once_with(document_id, "user-123")


def test_document_processing_route_requires_embedding_api_key(monkeypatch) -> None:
    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-123"}
    monkeypatch.setattr(settings, "openrouter_api_key", "")

    try:
        response = client.post(f"/api/v1/documents/{uuid4()}/process")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Embedding provider is not configured."}
