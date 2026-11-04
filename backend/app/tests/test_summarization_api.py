from __future__ import annotations

import json
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app, get_answer_client
from app.repositories.document_chunk_repository import DocumentChunkRepository


client = TestClient(app)


class ReplyClient:
    def __init__(self) -> None:
        self.replies = iter([
            json.dumps({"findings": [{"text": "Payment is due in 30 days.", "category": "obligation", "evidence_chunk_ids": ["c1"]}], "limitations": []}),
            json.dumps({"executive_summary": "Payment is due within 30 days.", "findings": [{"text": "Payment is due in 30 days.", "category": "obligation", "evidence_chunk_ids": ["c1"]}], "limitations": []}),
        ])

    def complete(self, messages: list[dict]) -> str:
        return next(self.replies)


def test_summary_route_requires_authentication() -> None:
    response = client.post(f"/api/v1/documents/{uuid4()}/summary", json={"style": "concise"})
    assert response.status_code == 401


def test_summary_route_hides_other_users_document() -> None:
    document_id = str(uuid4())
    repository = MagicMock(spec=DocumentChunkRepository)
    repository.get_owned_document.return_value = None
    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-123"}
    app.dependency_overrides[DocumentChunkRepository] = lambda: repository
    app.dependency_overrides[get_answer_client] = lambda: ReplyClient()
    try:
        response = client.post(f"/api/v1/documents/{document_id}/summary", json={"style": "concise"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


def test_summary_route_returns_structured_response() -> None:
    document_id = str(uuid4())
    repository = MagicMock(spec=DocumentChunkRepository)
    repository.get_owned_document.return_value = {"id": document_id, "status": "ready"}
    repository.list_chunks.return_value = [{
        "id": "c1", "document_id": document_id, "chunk_index": 0,
        "content": "Payment is due in 30 days.", "page_number": 3,
        "page_start": 3, "page_end": 3, "section_title": "Payment Terms",
    }]
    app.dependency_overrides[get_current_user] = lambda: {"sub": "user-123"}
    app.dependency_overrides[DocumentChunkRepository] = lambda: repository
    app.dependency_overrides[get_answer_client] = lambda: ReplyClient()
    try:
        response = client.post(f"/api/v1/documents/{document_id}/summary", json={"style": "concise"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == document_id
    assert body["style"] == "concise"
    assert body["findings"][0]["evidence"][0]["chunk_id"] == "c1"
    assert body["findings"][0]["evidence"][0]["page_number"] == 3
