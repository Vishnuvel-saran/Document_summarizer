from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import asdict
from typing import Any

from app.repositories.document_chunk_repository import (
    DocumentChunkRepository,
    DocumentNotFoundError,
)
from app.schemas.document_processing import DocumentProcessingResponse
from app.services.chunking import StructureAwareChunker
from app.services.document_parser import parse_docx, parse_pdf
from app.services.embeddings.base import EmbeddingProvider
from app.services.storage_service import SupabaseStorageService

logger = logging.getLogger(__name__)


class DocumentProcessingError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        super().__init__("Document processing failed.")
        self.error_code = error_code


class DocumentProcessingService:
    def __init__(
        self,
        *,
        repository: DocumentChunkRepository,
        storage: SupabaseStorageService,
        chunker: StructureAwareChunker,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.chunker = chunker
        self.embedding_provider = embedding_provider

    def process_document(
        self, document_id: str, owner_user_id: str
    ) -> DocumentProcessingResponse:
        document = self.repository.get_owned_document(document_id, owner_user_id)
        if document is None:
            raise DocumentNotFoundError("Document not found.")

        try:
            file_bytes = self.storage.download_document(document["storage_path"])
            if document["file_type"] == "pdf":
                extracted = parse_pdf(file_bytes, document["filename"])
            elif document["file_type"] == "docx":
                extracted = parse_docx(file_bytes, document["filename"])
            else:
                raise ValueError("Unsupported document type.")

            chunks = self.chunker.chunk_document(extracted, document_id)
            if not chunks:
                raise ValueError("Document extraction produced no chunks.")

            fingerprint = self._fingerprint(file_bytes, chunks)
            if (
                document.get("status") == "ready"
                and document.get("processing_fingerprint") == fingerprint
                and document.get("embedding_model") == self.embedding_provider.model_id
                and self.repository.count_chunks(document_id, owner_user_id)
                == len(chunks)
            ):
                return DocumentProcessingResponse(
                    document_id=document_id,
                    status="ready",
                    chunk_count=len(chunks),
                    embedding_model=self.embedding_provider.model_id,
                    skipped=True,
                )

            self.repository.mark_processing(document_id, owner_user_id)
            vectors = self.embedding_provider.embed_documents(
                [chunk.content for chunk in chunks]
            )
            self._validate_vectors(
                vectors, len(chunks), self.embedding_provider.dimension
            )
            self.repository.persist_chunks(
                document_id=document_id,
                user_id=owner_user_id,
                chunks=chunks,
                embeddings=vectors,
                model_id=self.embedding_provider.model_id,
                processing_fingerprint=fingerprint,
                dimension=self.embedding_provider.dimension,
            )
            return DocumentProcessingResponse(
                document_id=document_id,
                status="ready",
                chunk_count=len(chunks),
                embedding_model=self.embedding_provider.model_id,
            )
        except DocumentNotFoundError:
            raise
        except Exception as exc:
            error_code = type(exc).__name__
            logger.warning(
                "Document processing failed for %s (%s)", document_id, error_code
            )
            try:
                self.repository.mark_failed(document_id, owner_user_id, error_code)
            except Exception as status_error:
                logger.warning(
                    "Could not record processing failure for %s (%s)",
                    document_id,
                    type(status_error).__name__,
                )
            raise DocumentProcessingError(error_code) from exc

    @staticmethod
    def _validate_vectors(
        vectors: list[list[float]], expected_count: int, expected_dimension: int
    ) -> None:
        if len(vectors) != expected_count:
            raise ValueError("Embedding count does not match chunk count.")
        for vector in vectors:
            if len(vector) != expected_dimension or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in vector
            ):
                raise ValueError("Embedding vector has invalid values or dimension.")

    def _fingerprint(self, file_bytes: bytes, chunks: list[Any]) -> str:
        payload = {
            "file_sha256": hashlib.sha256(file_bytes).hexdigest(),
            "chunker": asdict(self.chunker.config),
            "chunks": [chunk.content_hash for chunk in chunks],
            "embedding_model": self.embedding_provider.model_id,
            "embedding_dimension": self.embedding_provider.dimension,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
