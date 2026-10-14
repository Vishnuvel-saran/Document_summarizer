import os
import uuid
from io import BytesIO

import fitz
import pytest
from sqlalchemy import text

from app.core.config import settings
from app.db import db_session
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.schemas.chunk import DocumentChunk
from app.services.chunking import ChunkingConfig, StructureAwareChunker
from app.services.document_processing_service import DocumentProcessingService
from app.services.storage_service import SupabaseStorageService


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SUPABASE_INTEGRATION") != "1",
    reason="Set RUN_SUPABASE_INTEGRATION=1 to run against the configured Supabase database.",
)


def _chunk(document_id: str, chunk_index: int) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        chunk_index=chunk_index,
        content=f"Integration chunk {chunk_index}",
        block_type="paragraph",
        page_number=1,
        page_start=1,
        page_end=1,
        section_title="Integration",
        source_block_indices=[chunk_index],
        source_metadata={"fixture": True},
        token_count=3,
        token_counting_method="tiktoken:cl100k_base",
        content_hash=f"hash-{chunk_index}",
    )


def test_pgvector_chunk_replacement_is_atomic_and_idempotent() -> None:
    repository = DocumentChunkRepository()
    document_id = str(uuid.uuid4())
    with db_session() as connection:
        user_id = connection.execute(
            text("SELECT id FROM auth.users LIMIT 1")
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO public.documents
                    (id, user_id, filename, file_type, storage_path, status)
                VALUES
                    (:id, :user_id, 'day4-integration.pdf', 'pdf', 'integration/test', 'uploaded')
                """
            ),
            {"id": document_id, "user_id": user_id},
        )

    try:
        chunks = [_chunk(document_id, 0), _chunk(document_id, 1)]
        vectors = [[0.0] * 1536, [0.1] * 1536]
        repository.persist_chunks(
            document_id,
            str(user_id),
            chunks,
            vectors,
            "test-embedding-model",
            "fingerprint-1",
            1536,
        )
        assert repository.count_chunks(document_id, str(user_id)) == 2
        assert len(repository.list_chunks(document_id, str(user_id))) == 2

        repository.persist_chunks(
            document_id,
            str(user_id),
            chunks,
            vectors,
            "test-embedding-model",
            "fingerprint-1",
            1536,
        )
        assert repository.count_chunks(document_id, str(user_id)) == 2

        duplicate_indices = [_chunk(document_id, 0), _chunk(document_id, 0)]
        with pytest.raises(Exception):
            repository.persist_chunks(
                document_id,
                str(user_id),
                duplicate_indices,
                vectors,
                "test-embedding-model",
                "fingerprint-2",
                1536,
            )
        assert repository.count_chunks(document_id, str(user_id)) == 2
        assert (
            repository.get_owned_document(
                document_id, "00000000-0000-0000-0000-000000000000"
            )
            is None
        )
    finally:
        with db_session() as connection:
            connection.execute(
                text("DELETE FROM public.documents WHERE id = :document_id"),
                {"document_id": document_id},
            )


class FakeEmbeddingProvider:
    model_id = "integration-fake-1536"
    dimension = 1536

    def __init__(self) -> None:
        self.calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[0.0] * self.dimension for _ in texts]


def _make_text_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Temporary live integration text for chunk provenance.")
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_real_storage_to_pgvector_processing_with_stub_embeddings() -> None:
    repository = DocumentChunkRepository()
    storage = SupabaseStorageService()
    provider = FakeEmbeddingProvider()
    document_id = str(uuid.uuid4())
    storage_path = None
    document_created = False

    with db_session() as connection:
        user_id = connection.execute(
            text("SELECT id FROM auth.users LIMIT 1")
        ).scalar_one()

    try:
        storage_path = storage.upload_document(
            str(user_id), document_id, "integration.pdf", _make_text_pdf(), "pdf"
        )
        with db_session() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO public.documents
                        (id, user_id, filename, file_type, storage_path, status)
                    VALUES
                        (:id, :user_id, 'integration.pdf', 'pdf', :storage_path, 'uploaded')
                    """
                ),
                {"id": document_id, "user_id": user_id, "storage_path": storage_path},
            )
        document_created = True

        service = DocumentProcessingService(
            repository=repository,
            storage=storage,
            chunker=StructureAwareChunker(
                ChunkingConfig(target_tokens=30, overlap_tokens=5, max_tokens=40)
            ),
            embedding_provider=provider,
        )
        result = service.process_document(document_id, str(user_id))
        repeated_result = service.process_document(document_id, str(user_id))
        rows = repository.list_chunks(document_id, str(user_id))

        assert result.status == "ready"
        assert result.chunk_count == 1
        assert repeated_result.skipped is True
        assert provider.calls == 1
        assert len(rows) == 1
        assert rows[0]["page_number"] == 1
        assert rows[0]["embedding_model"] == provider.model_id
        assert rows[0]["embedding_dimension"] == provider.dimension
    finally:
        if document_created:
            with db_session() as connection:
                connection.execute(
                    text("DELETE FROM public.documents WHERE id = :document_id"),
                    {"document_id": document_id},
                )
        if storage_path:
            from supabase import create_client

            client = create_client(
                settings.supabase_url, settings.supabase_service_role_key
            )
            client.storage.from_("documents").remove([storage_path])
