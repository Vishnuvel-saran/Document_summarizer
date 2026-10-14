from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    document_id: str
    chunk_index: int
    content: str
    block_type: str
    page_number: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    source_block_indices: list[int] = Field(default_factory=list)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    token_count: int
    token_counting_method: str
    content_hash: str
