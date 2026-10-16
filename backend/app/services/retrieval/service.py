from __future__ import annotations

from typing import Any

from app.repositories.document_chunk_repository import (
    DocumentChunkRepository,
)
from app.schemas.retrieval import RetrievalMode, DocumentSearchRequest
from app.services.embeddings.base import EmbeddingProvider


class RetrievalService:
    def __init__(
        self,
        repository: DocumentChunkRepository,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider
        # Lazy-initialize retrievers
        self._bm25: Any = None
        self._semantic: Any = None
        self._hybrid: Any = None

    @property
    def bm25(self) -> Any:
        if self._bm25 is None:
            from app.services.retrieval.bm25 import BM25Retriever
            self._bm25 = BM25Retriever(self.repository)
        return self._bm25

    @property
    def semantic(self) -> Any:
        if self._semantic is None:
            from app.services.retrieval.semantic import SemanticRetriever
            self._semantic = SemanticRetriever(
                self.repository, self.embedding_provider
            )
        return self._semantic

    @property
    def hybrid(self) -> Any:
        if self._hybrid is None:
            from app.services.retrieval.hybrid import HybridRetriever
            self._hybrid = HybridRetriever(
                self.repository, self.embedding_provider
            )
        return self._hybrid

    def search(self, request: DocumentSearchRequest, user_id: str) -> list[Any]:
        """
        Perform retrieval based on the requested mode.

        Args:
            request: The search request containing document_id, query, mode, and top_k
            user_id: The authenticated user's ID

        Returns:
            List of retrieval results appropriate for the mode
        """
        # Extract parameters
        document_id = request.document_id
        query = request.query
        mode = request.mode
        top_k = request.top_k

        # Route to appropriate retriever
        if mode == "bm25":
            return self.bm25.search(
                user_id=user_id,
                document_id=document_id,
                query=query,
                top_k=top_k,
            )
        elif mode == "semantic":
            return self.semantic.search(
                user_id=user_id,
                document_id=document_id,
                query=query,
                top_k=top_k,
            )
        elif mode == "hybrid":
            return self.hybrid.search(
                user_id=user_id,
                document_id=document_id,
                query=query,
                top_k=top_k,
            )
        else:
            raise ValueError(f"Unsupported retrieval mode: {mode}")