from __future__ import annotations

from app.repositories.document_chunk_repository import (
    DocumentChunkRepository,
    DocumentNotFoundError,
    DocumentNotReadyError,
)
from app.schemas.retrieval import RetrievalResult
from app.services.embeddings.base import EmbeddingProvider
from app.services.retrieval.hybrid import _reciprocal_rank_fusion, HybridRetriever


def _result(
    chunk_id: str,
    bm25_score: float | None = None,
    semantic_similarity: float | None = None,
) -> RetrievalResult:
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
        rank=0,  # Will be overwritten
        retrieval_mode="hybrid",
        bm25_score=bm25_score,
        semantic_similarity=semantic_similarity,
    )


class FakeRepository:
    def __init__(self, bm25_rows: list[RetrievalResult] | None = None) -> None:
        self._bm25_rows = bm25_rows
        self.calls = []

    def get_owned_document(self, document_id: str, user_id: str):
        self.calls.append(("owner", document_id, user_id))
        if user_id != "owner-1":
            return None
        return {"status": "ready", "embedding_model": "openai/text-embedding-3-small"}

    def ensure_embedding_compatibility(
        self, document_id: str, user_id: str, model_id: str, dimension: int
    ) -> bool:
        self.calls.append(("compatibility", document_id, model_id, dimension))
        return True

    def list_chunks(self, document_id: str, user_id: str) -> list[dict]:
        if self._bm25_rows is not None:
            return [
                {
                    "id": r.chunk_id,
                    "document_id": r.document_id,
                    "chunk_index": i,
                    "content": r.content,
                    "page_number": r.page_number,
                    "page_start": r.page_start,
                    "page_end": r.page_end,
                    "section_title": r.section_title,
                    "block_type": r.block_type,
                    "source_block_indices": r.source_block_indices,
                    "source_metadata": r.source_metadata,
                }
                for i, r in enumerate(self._bm25_rows)
            ]
        return []

    def semantic_search(
        self,
        document_id: str,
        user_id: str,
        query_vector: list[float],
        model_id: str,
        dimension: int,
        top_k: int,
    ):
        self.calls.append(("semantic", document_id, user_id, top_k))
        return []


class FakeEmbeddingProvider:
    model_id = "openai/text-embedding-3-small"
    dimension = 1536

    def __init__(self) -> None:
        self.queries = []

    def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return [0.1] * 1536

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1536 for _ in texts]


def test_rrf_fuses_two_rankings_correctly() -> None:
    """RRF should combine two ranked lists with correct score accumulation."""
    # BM25: c1 (rank 1), c2 (rank 2), c3 (rank 3)
    bm25_results = [
        _result("c1", bm25_score=10.0),
        _result("c2", bm25_score=5.0),
        _result("c3", bm25_score=2.0),
    ]
    # Semantic: c2 (rank 1), c1 (rank 2), c4 (rank 3)
    semantic_results = [
        _result("c2", semantic_similarity=0.9),
        _result("c1", semantic_similarity=0.8),
        _result("c4", semantic_similarity=0.7),
    ]

    fused = _reciprocal_rank_fusion(bm25_results, semantic_results, k0=60)

    # Expected RRF scores:
    # c1: 1/(60+1) + 1/(60+2) = 0.01639 + 0.01613 = 0.03252
    # c2: 1/(60+2) + 1/(60+1) = 0.01613 + 0.01639 = 0.03252
    # c3: 1/(60+3) + 0 = 0.01587
    # c4: 0 + 1/(60+3) = 0.01587

    assert len(fused) == 4
    # c1 and c2 should tie in RRF score; tie-break by chunk_id
    assert fused[0].chunk_id == "c1"
    assert fused[1].chunk_id == "c2"
    assert fused[2].chunk_id == "c3"
    assert fused[3].chunk_id == "c4"

    # Verify component ranks preserved
    assert fused[0].component_ranks == {"bm25": 1, "semantic": 2}
    assert fused[1].component_ranks == {"bm25": 2, "semantic": 1}
    assert fused[2].component_ranks == {"bm25": 3}
    assert fused[3].component_ranks == {"semantic": 3}


def test_rrf_handles_empty_rankings() -> None:
    """RRF should handle empty input lists gracefully."""
    fused = _reciprocal_rank_fusion([], [], k0=60)
    assert fused == []

    bm25_only = [_result("c1", bm25_score=10.0)]
    fused = _reciprocal_rank_fusion(bm25_only, [], k0=60)
    assert len(fused) == 1
    assert fused[0].chunk_id == "c1"
    assert fused[0].rrf_score == 1.0 / 61


def test_rrf_preserves_provenance() -> None:
    """RRF should preserve content and metadata from the original results."""
    bm25_results = [_result("c1", bm25_score=10.0)]
    semantic_results = [_result("c1", semantic_similarity=0.9)]

    fused = _reciprocal_rank_fusion(bm25_results, semantic_results, k0=60)

    assert fused[0].content == "Content for c1"
    assert fused[0].page_number == 1
    assert fused[0].section_title == "Test"


def test_hybrid_retriever_routes_to_sub_retrievers_and_fuses() -> None:
    """HybridRetriever should call both sub-retrievers and return fused results."""
    repository = FakeRepository(
        [
            _result("c1", bm25_score=10.0),
            _result("c2", bm25_score=5.0),
            _result("c3", bm25_score=2.0),
        ]
    )
    provider = FakeEmbeddingProvider()
    retriever = HybridRetriever(repository, provider)

    results = retriever.search(
        user_id="owner-1", document_id="doc-1", query="test query", top_k=3
    )

    # Verify both sub-retrievers were called
    call_types = [call[0] for call in repository.calls]
    assert "owner" in call_types
    assert "compatibility" in call_types
    assert "semantic" in call_types

    # Verify results are fused
    assert len(results) == 3
    assert all(r.retrieval_mode == "hybrid" for r in results)


def test_hybrid_retriever_rejects_other_owner() -> None:
    """HybridRetriever should reject non-owner before calling sub-retrievers."""
    repository = FakeRepository()
    provider = FakeEmbeddingProvider()
    retriever = HybridRetriever(repository, provider)

    try:
        retriever.search(
            user_id="owner-2", document_id="doc-1", query="test", top_k=3
        )
        assert False, "Expected ownership rejection"
    except LookupError:
        pass

    # Neither sub-retriever should have been called
    assert provider.queries == []


def test_hybrid_retriever_rejects_incompatible_model() -> None:
    """HybridRetriever should reject documents with incompatible embeddings."""
    repository = FakeRepository()

    def reject_compatibility(*args, **kwargs):
        raise DocumentNotReadyError("Embedding model mismatch.")

    repository.ensure_embedding_compatibility = reject_compatibility
    provider = FakeEmbeddingProvider()
    retriever = HybridRetriever(repository, provider)

    try:
        retriever.search(
            user_id="owner-1", document_id="doc-1", query="test", top_k=3
        )
        assert False, "Expected model mismatch error"
    except DocumentNotReadyError:
        pass

    assert provider.queries == []