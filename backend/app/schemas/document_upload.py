from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ExtractionSummary(BaseModel):
    block_count: int
    warnings: list[str] = Field(default_factory=list)


class DocumentUploadResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    status: str
    storage_path: str
    created_at: datetime | None = None
    extraction: ExtractionSummary
