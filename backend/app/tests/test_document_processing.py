from io import BytesIO

import fitz
import pytest

from app.repositories.document_chunk_repository import DocumentNotFoundError
from app.services.chunking import ChunkingConfig, StructureAwareChunker
from app.services.document_processing_service import (
    DocumentProcessingError,
    DocumentProcessingService,
)


class FakeRepository:
    def __init__(self) -> None:
        self.document = {
            "storage_path": "user-1/doc-1/source.pdf",
            "file_type": "pdf",
            "filename": "source.pdf",
            "status": "uploaded",
            "processing_fingerprint": None,
            "embedding_model": None,
        }
        self.chunks = []
        self.marked_failed = None
        self.persist_calls = 0

    def get_owned_document(self, document_id: str, user_id: str):
        if document_id != "doc-1" or user_id != "user-1":
            return None
        return dict(self.document)

    def count_chunks(self, document_id: str, user_id: str) -> int:
        return len(self.chunks)

    def mark_processing(self, document_id: str, user_id: str) -> None:
        self.document["status"] = "processing"

    def mark_failed(self, document_id: str, user_id: str, error_code: str) -> None:
        self.document["status"] = "failed"
        self.marked_failed = error_code

    def persist_chunks(self, **kwargs) -> None:
        self.persist_calls += 1
        self.chunks = kwargs["chunks"]
        self.document["status"] = "ready"
        self.document["processing_fingerprint"] = kwargs["processing_fingerprint"]
        self.document["embedding_model"] = kwargs["model_id"]


class FakeStorage:
    def __init__(self, file_bytes: bytes) -> None:
        self.file_bytes = file_bytes
        self.downloaded_paths = []

    def download_document(self, storage_path: str) -> bytes:
        self.downloaded_paths.append(storage_path)
        return self.file_bytes


class FakeEmbeddingProvider:
    model_id = "test-embedding-model"
    dimension = 3

    def __init__(self) -> None:
        self.calls = 0
        self.failure = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.failure:
            raise self.failure
        return [[float(index), 0.0, 1.0] for index, _ in enumerate(texts)]


def _make_pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "A contract paragraph with meaningful text.")
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _service(repository, storage, provider) -> DocumentProcessingService:
    return DocumentProcessingService(
        repository=repository,
        storage=storage,
        chunker=StructureAwareChunker(
            ChunkingConfig(target_tokens=40, overlap_tokens=5, max_tokens=48)
        ),
        embedding_provider=provider,
    )


def test_processing_runs_pdf_pipeline_and_persists_result() -> None:
    repository = FakeRepository()
    storage = FakeStorage(_make_pdf_bytes())
    provider = FakeEmbeddingProvider()

    result = _service(repository, storage, provider).process_document("doc-1", "user-1")

    assert result.status == "ready"
    assert result.chunk_count == 1
    assert result.embedding_model == provider.model_id
    assert repository.document["status"] == "ready"
    assert len(repository.chunks) == 1
    assert storage.downloaded_paths == ["user-1/doc-1/source.pdf"]


def test_processing_skips_embedding_when_fingerprint_is_unchanged() -> None:
    repository = FakeRepository()
    storage = FakeStorage(_make_pdf_bytes())
    provider = FakeEmbeddingProvider()
    service = _service(repository, storage, provider)

    first = service.process_document("doc-1", "user-1")
    second = service.process_document("doc-1", "user-1")

    assert first.skipped is False
    assert second.skipped is True
    assert provider.calls == 1
    assert repository.persist_calls == 1


def test_processing_rejects_other_users_before_storage_access() -> None:
    repository = FakeRepository()
    storage = FakeStorage(_make_pdf_bytes())
    provider = FakeEmbeddingProvider()

    with pytest.raises(DocumentNotFoundError):
        _service(repository, storage, provider).process_document("doc-1", "user-2")

    assert storage.downloaded_paths == []
    assert provider.calls == 0


def test_embedding_failure_marks_failed_without_replacing_previous_chunks() -> None:
    repository = FakeRepository()
    repository.chunks = ["previous-valid-chunks"]
    storage = FakeStorage(_make_pdf_bytes())
    provider = FakeEmbeddingProvider()
    provider.failure = RuntimeError("provider details should not escape")

    with pytest.raises(DocumentProcessingError) as error:
        _service(repository, storage, provider).process_document("doc-1", "user-1")

    assert error.value.error_code == "RuntimeError"
    assert "provider details" not in str(error.value)
    assert repository.chunks == ["previous-valid-chunks"]
    assert repository.document["status"] == "failed"
    assert repository.marked_failed == "RuntimeError"
    assert repository.persist_calls == 0
