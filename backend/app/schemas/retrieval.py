from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from pydantic import field_validator


RetrievalMode = Literal["bm25", "semantic", "hybrid"]


class RetrievalResult(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    page_number: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    block_type: str | None = None
    source_block_indices: list[int] = Field(default_factory=list)
    source_metadata: dict = Field(default_factory=dict)
    rank: int
    retrieval_mode: RetrievalMode
    bm25_score: float | None = None
    cosine_distance: float | None = None
    semantic_similarity: float | None = None
    rrf_score: float | None = None
    component_ranks: dict[str, int] = Field(default_factory=dict)


class DocumentSearchRequest(BaseModel):
    document_id: str
    query: str
    mode: RetrievalMode = "hybrid"
    top_k: int = Field(default=5, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Query must not be blank.")
        return v


class DocumentSearchResponse(BaseModel):
    document_id: str
    query: str
    mode: RetrievalMode
    results: list[RetrievalResult]


class DocumentAnswerRequest(BaseModel):
    query: str
    mode: RetrievalMode = "hybrid"
    top_k: int = Field(default=5, ge=1, le=20)


class DocumentAnswerResponse(BaseModel):
    document_id: str
    query: str
    mode: RetrievalMode
    answer: str
    cited_chunk_ids: list[str]
    invalid_citations: list[str]
    retrieved_chunks: list[RetrievalResult]

