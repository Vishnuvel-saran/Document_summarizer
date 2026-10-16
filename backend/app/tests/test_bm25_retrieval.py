from app.services.retrieval.bm25 import BM25Retriever


def _chunk(chunk_id: str, content: str, index: int) -> dict:
    return {
        "id": chunk_id,
        "document_id": "doc-1",
        "chunk_index": index,
        "content": content,
        "page_number": index + 1,
        "page_start": index + 1,
        "page_end": index + 1,
        "section_title": f"Section {index}",
        "block_type": "paragraph",
        "source_block_indices": [index],
        "source_metadata": {"origin": index},
    }


class FakeRepository:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.list_calls = 0

    def get_owned_document(self, document_id: str, user_id: str):
        if document_id == "doc-1" and user_id == "owner-1":
            return {"status": "ready"}
        return None

    def list_chunks(self, document_id: str, user_id: str) -> list[dict]:
        self.list_calls += 1
        return self.rows


def test_bm25_ranks_exact_terms_and_preserves_provenance() -> None:
    repository = FakeRepository(
        [
            _chunk("c1", "The agreement renews automatically each year.", 0),
            _chunk(
                "c2",
                "Either party must provide 30 days written notice before termination.",
                1,
            ),
            _chunk("c3", "Invoices are due within thirty calendar days.", 2),
        ]
    )
    retriever = BM25Retriever(repository)

    results = retriever.search(
        user_id="owner-1",
        document_id="doc-1",
        query="30 days written notice termination",
        top_k=2,
    )

    assert results[0].chunk_id == "c2"
    assert results[0].bm25_score is not None and results[0].bm25_score > 0
    assert results[0].page_number == 2
    assert results[0].section_title == "Section 1"
    assert results[0].source_block_indices == [1]
    assert results[0].retrieval_mode == "bm25"


def test_bm25_checks_owner_before_loading_and_handles_empty_corpus() -> None:
    repository = FakeRepository([])
    retriever = BM25Retriever(repository)

    assert (
        retriever.search(
            user_id="owner-1", document_id="doc-1", query="some words", top_k=5
        )
        == []
    )
    assert repository.list_calls == 1

    try:
        retriever.search(
            user_id="owner-2", document_id="doc-1", query="some words", top_k=5
        )
        assert False, "Expected ownership rejection"
    except LookupError:
        pass

    assert repository.list_calls == 1


def test_bm25_rejects_blank_query() -> None:
    retriever = BM25Retriever(FakeRepository([]))

    try:
        retriever.search(user_id="owner-1", document_id="doc-1", query="  ", top_k=5)
        assert False, "Expected blank query rejection"
    except ValueError as exc:
        assert "blank" in str(exc)
