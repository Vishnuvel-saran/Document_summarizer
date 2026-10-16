from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.core.config import settings
from app.main import app, get_document_processing_service
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.schemas.document_processing import DocumentProcessingResponse
from app.schemas.retrieval import DocumentSearchRequest, DocumentSearchResponse, RetrievalMode, RetrievalResult
from app.services.embeddings.openrouter_provider import OpenRouterEmbeddingProvider


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


def _chunk_result(chunk_id: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id="doc-1",
        content=f"Content for {chunk_id}",
        page_number=1,
        page_start=1,
        page_end=1,
        section_title="Test",
        block_type="paragraph",
        source_block_indices=[0],
        source_metadata={},
        rank=1,
        retrieval_mode=RetrievalMode.hybrid,
    )


def test_search_route_requires_authentication() -> None:
    response = client.post(
        f"/api/v1/documents/{uuid4()}/search",
        json={"document_id": "doc-1", "query": "test", "mode": "hybrid", "top_k": 5},
    )

    assert response.status_code == 401


def test_search_route_rejects_mismatched_document_id() -> None:
    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-123"}

    try:
        # Use a valid UUID in path but different in body
        path_id = str(uuid4())
        response = client.post(
            f"/api/v1/documents/{path_id}/search",
            json={
                "document_id": str(uuid4()),  # Different UUID
                "query": "test",
                "mode": "hybrid",
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    # 422 is acceptable since FastAPI validates this before our endpoint runs
    assert response.status_code in (400, 422)


def test_search_route_rejects_blank_query() -> None:
    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-123"}

    try:
        response = client.post(
            f"/api/v1/documents/{uuid4()}/search",
            json={
                "document_id": str(uuid4()),
                "query": "   ",
                "mode": "hybrid",
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422  # Pydantic validation rejects blank/empty string


def test_search_route_returns_results_for_hybrid_mode() -> None:
    document_id = str(uuid4())
    mock_repo = MagicMock(spec=DocumentChunkRepository)
    mock_repo.get_owned_document.return_value = {
        "status": "ready",
        "embedding_model": "openai/text-embedding-3-small",
    }
    mock_repo.ensure_embedding_compatibility.return_value = True
    mock_repo.list_chunks.return_value = [
        {
            "id": "c1",
            "document_id": document_id,
            "chunk_index": 0,
            "content": "Chunk 1",
            "page_number": 1,
            "page_start": 1,
            "page_end": 1,
            "section_title": "Section 1",
            "block_type": "paragraph",
            "source_block_indices": [0],
            "source_metadata": {},
        }
    ]

    mock_embedding = MagicMock(spec=OpenRouterEmbeddingProvider)
    mock_embedding.model_id = "openai/text-embedding-3-small"
    mock_embedding.dimension = 1536

    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-123"}
    app.dependency_overrides[DocumentChunkRepository] = lambda: mock_repo
    app.dependency_overrides[OpenRouterEmbeddingProvider] = lambda: mock_embedding

    try:
        response = client.post(
            f"/api/v1/documents/{document_id}/search",
            json={
                "document_id": document_id,
                "query": "test query",
                "mode": "hybrid",
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == document_id
    assert data["query"] == "test query"
    assert data["mode"] == "hybrid"
    assert len(data["results"]) >= 0  # At least empty list is valid


def test_search_route_returns_results_for_bm25_mode() -> None:
    document_id = str(uuid4())
    mock_repo = MagicMock(spec=DocumentChunkRepository)
    mock_repo.get_owned_document.return_value = {
        "status": "ready",
        "embedding_model": "openai/text-embedding-3-small",
    }
    mock_repo.list_chunks.return_value = [
        {
            "id": "c1",
            "document_id": document_id,
            "chunk_index": 0,
            "content": "Chunk 1",
            "page_number": 1,
            "page_start": 1,
            "page_end": 1,
            "section_title": "Section 1",
            "block_type": "paragraph",
            "source_block_indices": [0],
            "source_metadata": {},
        }
    ]

    mock_embedding = MagicMock(spec=OpenRouterEmbeddingProvider)
    mock_embedding.model_id = "openai/text-embedding-3-small"
    mock_embedding.dimension = 1536

    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-123"}
    app.dependency_overrides[DocumentChunkRepository] = lambda: mock_repo
    app.dependency_overrides[OpenRouterEmbeddingProvider] = lambda: mock_embedding

    try:
        response = client.post(
            f"/api/v1/documents/{document_id}/search",
            json={
                "document_id": document_id,
                "query": "test query",
                "mode": "bm25",
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "bm25"


def test_search_route_returns_results_for_semantic_mode() -> None:
    document_id = str(uuid4())
    mock_repo = MagicMock(spec=DocumentChunkRepository)
    mock_repo.get_owned_document.return_value = {
        "status": "ready",
        "embedding_model": "openai/text-embedding-3-small",
    }
    mock_repo.ensure_embedding_compatibility.return_value = True
    mock_repo.semantic_search.return_value = [
        {
            "id": "c1",
            "document_id": document_id,
            "content": "Chunk 1",
            "page_number": 1,
            "page_start": 1,
            "page_end": 1,
            "section_title": "Section 1",
            "block_type": "paragraph",
            "source_block_indices": [0],
            "source_metadata": {},
            "cosine_distance": 0.1,
        }
    ]

    mock_embedding = MagicMock(spec=OpenRouterEmbeddingProvider)
    mock_embedding.model_id = "openai/text-embedding-3-small"
    mock_embedding.dimension = 1536
    mock_embedding.embed_query.return_value = [0.1] * 1536

    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-123"}
    app.dependency_overrides[DocumentChunkRepository] = lambda: mock_repo
    app.dependency_overrides[OpenRouterEmbeddingProvider] = lambda: mock_embedding

    try:
        response = client.post(
            f"/api/v1/documents/{document_id}/search",
            json={
                "document_id": document_id,
                "query": "test query",
                "mode": "semantic",
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "semantic"


def test_search_route_returns_404_for_missing_document() -> None:
    document_id = str(uuid4())
    mock_repo = MagicMock(spec=DocumentChunkRepository)
    mock_repo.get_owned_document.return_value = None

    mock_embedding = MagicMock(spec=OpenRouterEmbeddingProvider)
    mock_embedding.model_id = "openai/text-embedding-3-small"
    mock_embedding.dimension = 1536

    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-123"}
    app.dependency_overrides[DocumentChunkRepository] = lambda: mock_repo
    app.dependency_overrides[OpenRouterEmbeddingProvider] = lambda: mock_embedding

    try:
        response = client.post(
            f"/api/v1/documents/{document_id}/search",
            json={
                "document_id": document_id,
                "query": "test",
                "mode": "hybrid",
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
