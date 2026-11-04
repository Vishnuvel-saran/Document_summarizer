from typing import Literal

from pydantic import BaseModel, Field, field_validator


class EvidenceReference(BaseModel):
    chunk_id: str
    page_number: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None


FindingCategory = Literal[
    "main_point",
    "qualification",
    "exception",
    "date",
    "amount",
    "obligation",
    "risk",
    "other",
]


class SummaryFinding(BaseModel):
    text: str
    category: FindingCategory = "main_point"
    evidence: list[EvidenceReference] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def text_must_be_present(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Finding text must not be blank.")
        return value.strip()


class DocumentSummaryRequest(BaseModel):
    style: Literal["concise", "detailed"] = "concise"


class DocumentSummaryResponse(BaseModel):
    document_id: str
    style: Literal["concise", "detailed"]
    executive_summary: str
    findings: list[SummaryFinding] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    map_group_count: int
    reduction_level_count: int
