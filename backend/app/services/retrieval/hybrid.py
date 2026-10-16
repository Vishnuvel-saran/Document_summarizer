from __future__ import annotations

from typing import Any

from app.repositories.document_chunk_repository import (
    DocumentChunkRepository,
    DocumentNotFoundError,
    DocumentNotReadyError,
)
from app.schemas.retrieval import RetrievalResult
from app.services.embeddings.base import EmbeddingProvider


def _reciprocal_rank_fusion(
    *ranked_lists: list[RetrievalResult],
    k0: int = 60,
) -> list[RetrievalResult]:
    """
    Combine multiple ranked result lists using Reciprocal Rank Fusion (RRF).

    For each chunk d:
        RRF(d) = sum_{r in R} 1 / (k0 + rank_r(d))

    where R is the set of rankings (e.g., BM25, semantic) and rank_r(d) is the
    position of chunk d in ranking r (1-indexed). Chunks not present in a
    ranking contribute 0 for that ranking.

    Returns a new list sorted by RRF score descending, with tie-breaking by
    chunk_id for determinism.
    """
    # Map chunk_id -> accumulated RRF score
    rrf_scores: dict[str, float] = {}
    # Map chunk_id -> best result object (to preserve provenance)
    best_result: dict[str, RetrievalResult] = {}
    # Map chunk_id -> component ranks (e.g., {"bm25": 3, "semantic": 5})
    component_ranks: dict[str, dict[str, int]] = {}

    for ranking in ranked_lists:
        for rank, result in enumerate(ranking, start=1):
            chunk_id = result.chunk_id
            # Accumulate RRF contribution
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (k0 + rank)
            # Keep the result with the highest individual score as the "best"
            # (this preserves provenance like content, page numbers, etc.)
            if chunk_id not in best_result:
                best_result[chunk_id] = result
            else:
                # Prefer the result with a non-null score in either BM25 or semantic
                current = best_result[chunk_id]
                if (result.bm25_score is not None and current.bm25_score is None) or \
                   (result.semantic_similarity is not None and current.semantic_similarity is None):
                    best_result[chunk_id] = result
            # Track component ranks
            if chunk_id not in component_ranks:
                component_ranks[chunk_id] = {}
            # Determine which ranking this is by checking which score is present
            if result.bm25_score is not None:
                component_ranks[chunk_id]["bm25"] = rank
            elif result.semantic_similarity is not None:
                component_ranks[chunk_id]["semantic"] = rank

    # Build final results sorted by RRF score descending
    final_results: list[RetrievalResult] = []
    for chunk_id in sorted(rrf_scores.keys(), key=lambda cid: (-rrf_scores[cid], cid)):
        result = best_result[chunk_id].model_copy()
        result.rrf_score = rrf_scores[chunk_id]
        result.component_ranks = component_ranks.get(chunk_id, {})
        result.retrieval_mode = "hybrid"
        result.rank = 0  # Will be assigned after sorting
        final_results.append(result)

    # Assign final ranks
    for final_rank, result in enumerate(final_results, start=1):
        result.rank = final_rank

    return final_results


class HybridRetriever:
    def __init__(
        self,
        repository: DocumentChunkRepository,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider
        # Lazy-initialize sub-retrievers to avoid circular dependencies
        self._bm25: Any = None
        self._semantic: Any = None

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

    def search(
        self, *, user_id: str, document_id: str, query: str, top_k: int
    ) -> list[RetrievalResult]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("Query must not be blank.")

        # Retrieve more candidates than needed to improve fusion quality
        # Configurable: 2x top_k with a minimum of 10 and maximum of 50
        candidate_count = max(10, min(50, top_k * 2))

        # Get results from both retrievers
        bm25_results = self.bm25.search(
            user_id=user_id,
            document_id=document_id,
            query=normalized_query,
            top_k=candidate_count,
        )
        semantic_results = self.semantic.search(
            user_id=user_id,
            document_id=document_id,
            query=normalized_query,
            top_k=candidate_count,
        )

        # Fuse using RRF
        fused = _reciprocal_rank_fusion(bm25_results, semantic_results, k0=60)

        # Return exactly top_k results
        return fused[:top_k]