from __future__ import annotations

from app.repositories.document_chunk_repository import (
    DocumentChunkRepository,
    DocumentNotFoundError,
    DocumentNotReadyError,
)
from app.schemas.retrieval import RetrievalResult
from app.services.embeddings.base import EmbeddingProvider


class SemanticRetriever:
    def __init__(
        self,
        repository: DocumentChunkRepository,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider

    def search(
        self, *, user_id: str, document_id: str, query: str, top_k: int
    ) -> list[RetrievalResult]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("Query must not be blank.")

        document = self.repository.get_owned_document(document_id, user_id)
        if document is None:
            raise DocumentNotFoundError("Document not found.")
        if document.get("status") != "ready":
            raise DocumentNotReadyError("Document is not ready for retrieval.")

        has_vectors = self.repository.ensure_embedding_compatibility(
            document_id,
            user_id,
            self.embedding_provider.model_id,
            self.embedding_provider.dimension,
        )
        if not has_vectors:
            return []

        query_vector = self.embedding_provider.embed_query(normalized_query)
        rows = self.repository.semantic_search(
            document_id,
            user_id,
            query_vector,
            self.embedding_provider.model_id,
            self.embedding_provider.dimension,
            top_k,
        )
        return [
            RetrievalResult(
                chunk_id=str(row["id"]),
                document_id=str(row["document_id"]),
                content=row["content"],
                page_number=row["page_number"],
                page_start=row["page_start"],
                page_end=row["page_end"],
                section_title=row["section_title"],
                block_type=row["block_type"],
                source_block_indices=row["source_block_indices"] or [],
                source_metadata=row["source_metadata"] or {},
                rank=rank,
                retrieval_mode="semantic",
                cosine_distance=float(row["cosine_distance"]),
                semantic_similarity=1.0 - float(row["cosine_distance"]),
            )
            for rank, row in enumerate(rows, start=1)
        ]
