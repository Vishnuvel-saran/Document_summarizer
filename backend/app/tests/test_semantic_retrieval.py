from app.repositories.document_chunk_repository import (
    EmbeddingModelMismatchError,
)
from app.services.retrieval.semantic import SemanticRetriever


class FakeRepository:
    def __init__(self) -> None:
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
        return [
            {
                "id": "chunk-1",
                "document_id": document_id,
                "content": "Notice must be given 30 days before termination.",
                "page_number": 4,
                "page_start": 4,
                "page_end": 4,
                "section_title": "Termination",
                "block_type": "paragraph",
                "source_block_indices": [8],
                "source_metadata": {"blocks": [{"block_index": 8}]},
                "cosine_distance": 0.12,
            }
        ]


class FakeEmbeddingProvider:
    model_id = "openai/text-embedding-3-small"
    dimension = 3

    def __init__(self) -> None:
        self.queries = []

    def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return [0.1, 0.2, 0.3]


def test_semantic_retriever_checks_owner_and_model_before_embedding() -> None:
    repository = FakeRepository()
    provider = FakeEmbeddingProvider()
    retriever = SemanticRetriever(repository, provider)

    results = retriever.search(
        user_id="owner-1", document_id="doc-1", query="notice period", top_k=5
    )

    assert provider.queries == ["notice period"]
    assert repository.calls[0] == ("owner", "doc-1", "owner-1")
    assert repository.calls[1] == (
        "compatibility",
        "doc-1",
        "openai/text-embedding-3-small",
        3,
    )
    assert results[0].chunk_id == "chunk-1"
    assert results[0].rank == 1
    assert results[0].semantic_similarity == 0.88
    assert results[0].retrieval_mode == "semantic"
    assert results[0].page_number == 4
    assert results[0].source_block_indices == [8]


def test_semantic_retriever_rejects_other_owner_before_embedding() -> None:
    repository = FakeRepository()
    provider = FakeEmbeddingProvider()
    retriever = SemanticRetriever(repository, provider)

    try:
        retriever.search(
            user_id="owner-2", document_id="doc-1", query="secret", top_k=5
        )
        assert False, "Expected missing-document error for non-owner"
    except LookupError:
        pass

    assert provider.queries == []


def test_semantic_retriever_does_not_embed_incompatible_model() -> None:
    repository = FakeRepository()
    provider = FakeEmbeddingProvider()

    def reject_compatibility(*args, **kwargs):
        raise EmbeddingModelMismatchError("Embedding model mismatch.")

    repository.ensure_embedding_compatibility = reject_compatibility
    retriever = SemanticRetriever(repository, provider)

    try:
        retriever.search(
            user_id="owner-1", document_id="doc-1", query="notice", top_k=5
        )
        assert False, "Expected model mismatch"
    except EmbeddingModelMismatchError:
        pass

    assert provider.queries == []
