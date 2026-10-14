from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy import text

from app import db as db_module
from app.schemas.chunk import DocumentChunk


class DocumentNotFoundError(LookupError):
    pass


class DocumentChunkRepository:
    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Any]] | None = None,
    ) -> None:
        self._session_factory = session_factory or db_module.db_session

    def get_owned_document(
        self, document_id: str, user_id: str
    ) -> dict[str, Any] | None:
        with self._session_factory() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT id, user_id, filename, file_type, storage_path, status,
                           processing_fingerprint, embedding_model
                    FROM public.documents
                    WHERE id = :document_id AND user_id = :user_id
                    """
                    ),
                    {"document_id": document_id, "user_id": user_id},
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def mark_processing(self, document_id: str, user_id: str) -> None:
        with self._session_factory() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE public.documents
                    SET status = 'processing', processing_error = NULL, updated_at = NOW()
                    WHERE id = :document_id AND user_id = :user_id
                    """
                ),
                {"document_id": document_id, "user_id": user_id},
            )
            if result.rowcount != 1:
                raise DocumentNotFoundError("Document not found.")

    def mark_failed(self, document_id: str, user_id: str, error_code: str) -> None:
        safe_code = (
            re.sub(r"[^A-Za-z0-9_.-]", "_", error_code)[:64] or "ProcessingError"
        )
        with self._session_factory() as connection:
            connection.execute(
                text(
                    """
                    UPDATE public.documents
                    SET status = 'failed', processing_error = :error_code, updated_at = NOW()
                    WHERE id = :document_id AND user_id = :user_id
                    """
                ),
                {
                    "document_id": document_id,
                    "user_id": user_id,
                    "error_code": safe_code,
                },
            )

    def persist_chunks(
        self,
        document_id: str,
        user_id: str,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        model_id: str,
        processing_fingerprint: str,
        dimension: int,
    ) -> None:
        if not chunks:
            raise ValueError("Cannot persist an empty chunk set.")
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk and embedding counts do not match.")
        if not model_id or dimension <= 0:
            raise ValueError("Embedding model and dimension are required.")

        parameters: list[dict[str, Any]] = []
        for chunk, vector in zip(chunks, embeddings, strict=True):
            if chunk.document_id != document_id:
                raise ValueError(
                    "Chunk document ID does not match the target document."
                )
            if len(vector) != dimension or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in vector
            ):
                raise ValueError(
                    "Embedding vector is malformed or has the wrong dimension."
                )
            parameters.append(
                {
                    "document_id": document_id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "page_number": chunk.page_number,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "section_title": chunk.section_title,
                    "block_type": chunk.block_type,
                    "source_block_indices": json.dumps(chunk.source_block_indices),
                    "source_metadata": json.dumps(chunk.source_metadata),
                    "token_count": chunk.token_count,
                    "token_counting_method": chunk.token_counting_method,
                    "content_hash": chunk.content_hash,
                    "embedding": "["
                    + ",".join(format(value, ".9g") for value in vector)
                    + "]",
                    "embedding_model": model_id,
                    "embedding_dimension": dimension,
                }
            )

        with self._session_factory() as connection:
            updated = connection.execute(
                text(
                    """
                    UPDATE public.documents
                    SET status = 'ready', processing_error = NULL,
                        processing_fingerprint = :processing_fingerprint,
                        embedding_model = :embedding_model, updated_at = NOW()
                    WHERE id = :document_id AND user_id = :user_id
                    RETURNING id
                    """
                ),
                {
                    "document_id": document_id,
                    "user_id": user_id,
                    "processing_fingerprint": processing_fingerprint,
                    "embedding_model": model_id,
                },
            ).first()
            if updated is None:
                raise DocumentNotFoundError("Document not found.")

            connection.execute(
                text(
                    "DELETE FROM public.document_chunks WHERE document_id = :document_id"
                ),
                {"document_id": document_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO public.document_chunks (
                        document_id, chunk_index, content, page_number, page_start, page_end,
                        section_title, block_type, source_block_indices, source_metadata,
                        token_count, token_counting_method, content_hash, embedding,
                        embedding_model, embedding_dimension
                    ) VALUES (
                        :document_id, :chunk_index, :content, :page_number, :page_start,
                        :page_end, :section_title, :block_type,
                        CAST(:source_block_indices AS jsonb), CAST(:source_metadata AS jsonb),
                        :token_count, :token_counting_method, :content_hash,
                        CAST(:embedding AS vector(1536)), :embedding_model, :embedding_dimension
                    )
                    """
                ),
                parameters,
            )

    def count_chunks(self, document_id: str, user_id: str) -> int:
        with self._session_factory() as connection:
            return int(
                connection.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM public.document_chunks c
                        JOIN public.documents d ON d.id = c.document_id
                        WHERE c.document_id = :document_id AND d.user_id = :user_id
                        """
                    ),
                    {"document_id": document_id, "user_id": user_id},
                ).scalar_one()
            )

    def list_chunks(self, document_id: str, user_id: str) -> list[dict[str, Any]]:
        with self._session_factory() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                    SELECT c.id, c.chunk_index, c.content, c.page_number, c.page_start,
                           c.page_end, c.section_title, c.block_type,
                           c.source_block_indices, c.source_metadata, c.token_count,
                           c.token_counting_method, c.content_hash, c.embedding_model,
                           c.embedding_dimension
                    FROM public.document_chunks c
                    JOIN public.documents d ON d.id = c.document_id
                    WHERE c.document_id = :document_id AND d.user_id = :user_id
                    ORDER BY c.chunk_index
                    """
                    ),
                    {"document_id": document_id, "user_id": user_id},
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]
