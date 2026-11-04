from __future__ import annotations

import json

import pytest

from app.services.answer.client import AnswerClientError
from app.services.summarization import (
    EmptyDocumentError,
    EvidenceValidationError,
    HierarchicalSummarizationService,
    SummarizationError,
)


class FakeClient:
    def __init__(self, replies: list[str], error: AnswerClientError | None = None) -> None:
        self.replies = list(replies)
        self.error = error
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict]) -> str:
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.replies.pop(0)


def _chunk(chunk_id: str, content: str, page: int | None = 2, section: str | None = "Terms") -> dict:
    return {
        "id": chunk_id,
        "document_id": "doc-1",
        "chunk_index": int(chunk_id[-1]) if chunk_id[-1:].isdigit() else 0,
        "content": content,
        "page_number": page,
        "page_start": page,
        "page_end": page,
        "section_title": section,
    }


def test_short_document_returns_structured_summary_and_database_metadata() -> None:
    replies = [
        json.dumps({"findings": [{"text": "Payment is due in 30 days.", "category": "obligation", "evidence_chunk_ids": ["c1"]}], "limitations": []}),
        json.dumps({"executive_summary": "The agreement requires payment within 30 days.", "findings": [{"text": "Payment is due in 30 days.", "category": "obligation", "evidence_chunk_ids": ["c1"]}], "limitations": []}),
    ]
    service = HierarchicalSummarizationService(FakeClient(replies))
    result = service.summarize(document_id="doc-1", style="concise", chunks=[_chunk("c1", "Payment is due in 30 days.")])

    assert result.executive_summary.startswith("The agreement")
    assert result.findings[0].evidence[0].chunk_id == "c1"
    assert result.findings[0].evidence[0].page_number == 2
    assert result.findings[0].evidence[0].section_title == "Terms"


def test_long_document_creates_multiple_map_groups_and_preserves_order() -> None:
    client = FakeClient([])
    service = HierarchicalSummarizationService(client, map_max_chars=20)
    chunk = _chunk("c1", "A" * 45)
    groups = service._group_chunks([chunk])
    assert len(groups) == 3
    assert [group[0]["chunk_id"] for group in groups] == ["c1", "c1", "c1"]


def test_multiple_reduction_levels() -> None:
    intermediate = [{"text": ("A" * 100) + str(i), "category": "main_point", "evidence_chunk_ids": ["c1"]} for i in range(4)]
    compact = [{"text": "Combined finding", "category": "main_point", "evidence_chunk_ids": ["c1"]}]
    client = FakeClient([
        json.dumps({"executive_summary": "Reduced", "findings": compact, "limitations": []}),
        json.dumps({"executive_summary": "Reduced", "findings": compact, "limitations": []}),
        json.dumps({"executive_summary": "Final summary", "findings": compact, "limitations": []}),
    ])
    service = HierarchicalSummarizationService(client, reduce_max_chars=400)
    levels, final = service._reduce_intermediate(intermediate, "detailed")
    assert levels >= 1
    assert final["executive_summary"] == "Final summary"


def test_chunk_order_is_preserved_in_map_grouping() -> None:
    service = HierarchicalSummarizationService(FakeClient([]), map_max_chars=100)
    groups = service._group_chunks([_chunk("c1", "First"), _chunk("c2", "Second")])
    assert [item["chunk_id"] for item in groups[0]] == ["c1", "c2"]


def test_fabricated_evidence_id_is_rejected() -> None:
    replies = [json.dumps({"findings": [{"text": "Invented fact", "category": "main_point", "evidence_chunk_ids": ["fake"]}], "limitations": []})]
    service = HierarchicalSummarizationService(FakeClient(replies))
    with pytest.raises(EvidenceValidationError):
        service.summarize(document_id="doc-1", style="concise", chunks=[_chunk("c1", "Real text")])


def test_empty_document_is_controlled_error() -> None:
    service = HierarchicalSummarizationService(FakeClient([]))
    with pytest.raises(EmptyDocumentError, match="no usable"):
        service.summarize(document_id="doc-1", style="concise", chunks=[_chunk("c1", "   ")])


def test_missing_metadata_is_represented_as_none() -> None:
    reply = json.dumps({"findings": [{"text": "A point", "category": "main_point", "evidence_chunk_ids": ["c1"]}], "limitations": []})
    final = json.dumps({"executive_summary": "Summary", "findings": [{"text": "A point", "category": "main_point", "evidence_chunk_ids": ["c1"]}], "limitations": []})
    service = HierarchicalSummarizationService(FakeClient([reply, final]))
    result = service.summarize(document_id="doc-1", style="detailed", chunks=[_chunk("c1", "A point", page=None, section=None)])
    evidence = result.findings[0].evidence[0]
    assert evidence.page_number is None
    assert evidence.section_title is None


def test_malformed_model_response_is_clean_error() -> None:
    service = HierarchicalSummarizationService(FakeClient(["not json"]))
    with pytest.raises(SummarizationError, match="malformed structured output"):
        service.summarize(document_id="doc-1", style="concise", chunks=[_chunk("c1", "Text")])


def test_provider_error_is_bounded_and_sanitized() -> None:
    client = FakeClient([], AnswerClientError("Provider timeout details"))
    service = HierarchicalSummarizationService(client)
    with pytest.raises(SummarizationError, match="provider request failed"):
        service.summarize(document_id="doc-1", style="concise", chunks=[_chunk("c1", "Text")])
    assert len(client.calls) == 2


def test_concise_and_detailed_styles_are_accepted() -> None:
    for style in ("concise", "detailed"):
        replies = [
            json.dumps({"findings": [{"text": "Point", "category": "main_point", "evidence_chunk_ids": ["c1"]}], "limitations": []}),
            json.dumps({"executive_summary": "Summary", "findings": [{"text": "Point", "category": "main_point", "evidence_chunk_ids": ["c1"]}], "limitations": []}),
        ]
        result = HierarchicalSummarizationService(FakeClient(replies)).summarize(document_id="doc-1", style=style, chunks=[_chunk("c1", "Point")])
        assert result.style == style


def test_exception_and_qualification_remain_in_findings() -> None:
    reply = json.dumps({"findings": [
        {"text": "Renewal occurs annually.", "category": "main_point", "evidence_chunk_ids": ["c1"]},
        {"text": "Cancellation is allowed only for material breach.", "category": "exception", "evidence_chunk_ids": ["c1"]},
    ], "limitations": []})
    final = json.dumps({"executive_summary": "Annual renewal with a material-breach cancellation exception.", "findings": json.loads(reply)["findings"], "limitations": []})
    result = HierarchicalSummarizationService(FakeClient([reply, final])).summarize(document_id="doc-1", style="detailed", chunks=[_chunk("c1", "Renewal occurs annually; cancellation only for material breach.")])
    assert any(f.category == "exception" for f in result.findings)
