from __future__ import annotations

from typing import Any

from rank_bm25 import BM25Okapi

from app.repositories.document_chunk_repository import (
    DocumentChunkRepository,
    DocumentNotFoundError,
    DocumentNotReadyError,
)
from app.schemas.retrieval import RetrievalResult


def _tokenize(text: str) -> list[str]:
    """Simple tokenization: lowercasing and splitting on whitespace."""
    return text.lower().split()


class BM25Retriever:
    def __init__(self, repository: DocumentChunkRepository) -> None:
        self.repository = repository

    def search(
        self, *, user_id: str, document_id: str, query: str, top_k: int
    ) -> list[RetrievalResult]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("Query must not be blank.")

        # 1. Ownership and readiness check
        document = self.repository.get_owned_document(document_id, user_id)
        if document is None:
            raise DocumentNotFoundError("Document not found.")
        if document.get("status") != "ready":
            raise DocumentNotReadyError("Document is not ready for retrieval.")

        # 2. Load chunks for the document (already filtered by ownership in repository)
        chunks = self.repository.list_chunks(document_id, user_id)
        if not chunks:
            return []

        # 3. Tokenize chunk content
        tokenized_corpus = [_tokenize(chunk["content"]) for chunk in chunks]

        # 4. Build BM25 index
        bm25 = BM25Okapi(tokenized_corpus)

        # 5. Tokenize query and get scores
        tokenized_query = _tokenize(normalized_query)
        scores = bm25.get_scores(tokenized_query)

        # 6. Rank chunks by score descending, break ties by chunk_index for determinism
        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: (-scores[i], chunks[i]["chunk_index"]),
        )

        # 7. Take top_k
        top_indices = ranked_indices[:top_k]

        # 8. Build results
        results: list[RetrievalResult] = []
        for rank, idx in enumerate(top_indices, start=1):
            chunk = chunks[idx]
            results.append(
                RetrievalResult(
                    chunk_id=str(chunk["id"]),
                    document_id=str(chunk["document_id"]),
                    content=chunk["content"],
                    page_number=chunk["page_number"],
                    page_start=chunk["page_start"],
                    page_end=chunk["page_end"],
                    section_title=chunk["section_title"],
                    block_type=chunk["block_type"],
                    source_block_indices=chunk["source_block_indices"] or [],
                    source_metadata=chunk["source_metadata"] or {},
                    rank=rank,
                    retrieval_mode="bm25",
                    bm25_score=float(scores[idx]),
                )
            )
        return results