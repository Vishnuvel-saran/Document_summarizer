from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.schemas.summary import DocumentSummaryResponse, EvidenceReference, SummaryFinding
from app.services.answer.client import AnswerClientError


logger = logging.getLogger("document_intelligence_api")


class SummarizationError(RuntimeError):
    pass


class EmptyDocumentError(SummarizationError):
    pass


class EvidenceValidationError(SummarizationError):
    pass


class _MapOutput(BaseModel):
    findings: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class _ReduceOutput(BaseModel):
    executive_summary: str
    findings: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


_MAP_SYSTEM_PROMPT = """You create evidence-grounded findings from supplied document chunks.
Use only supplied text. Do not invent facts, dates, amounts, obligations, risks, legal interpretations, or conclusions.
Preserve exceptions, conditions, limitations, and qualifications. If information is missing, state it in limitations.
Return only valid JSON with this shape:
{"findings":[{"text":"...","category":"main_point|qualification|exception|date|amount|obligation|risk|other","evidence_chunk_ids":["chunk-id"]}],"limitations":["..."]}
Do not invent chunk IDs or page/section metadata. Associate each substantive finding with the original supplied chunk ID(s).
"""

_REDUCE_SYSTEM_PROMPT = """You reduce intermediate findings into one coherent document summary.
Use only the supplied findings. Preserve original evidence_chunk_ids. Do not invent facts, chunk IDs, page numbers, or section titles.
Do not present interpretations as explicit statements. Merge duplicates and preserve exceptions and qualifications.
Return only valid JSON with this shape:
{"executive_summary":"...","findings":[{"text":"...","category":"main_point|qualification|exception|date|amount|obligation|risk|other","evidence_chunk_ids":["chunk-id"]}],"limitations":["..."]}
"""


class HierarchicalSummarizationService:
    def __init__(
        self,
        client: Any,
        *,
        map_max_chars: int = 12000,
        reduce_max_chars: int = 12000,
        max_reduction_levels: int = 4,
    ) -> None:
        if map_max_chars <= 0 or reduce_max_chars <= 0 or max_reduction_levels < 1:
            raise ValueError("Summarization limits must be positive.")
        self.client = client
        self.map_max_chars = map_max_chars
        self.reduce_max_chars = reduce_max_chars
        self.max_reduction_levels = max_reduction_levels

    def summarize(
        self,
        *,
        document_id: str,
        style: str,
        chunks: list[dict[str, Any]],
    ) -> DocumentSummaryResponse:
        usable = [chunk for chunk in chunks if str(chunk.get("content") or "").strip()]
        if not usable:
            raise EmptyDocumentError("The document has no usable extracted text.")

        metadata_by_id: dict[str, dict[str, Any]] = {}
        for chunk in usable:
            chunk_id = str(chunk.get("id") or chunk.get("chunk_id") or "")
            if not chunk_id:
                raise SummarizationError("A document chunk is missing its ID.")
            metadata_by_id[chunk_id] = chunk

        groups = self._group_chunks(usable)
        intermediate_findings: list[dict[str, Any]] = []
        all_limitations: list[str] = []

        for group in groups:
            payload = json.dumps(
                {
                    "style": style,
                    "chunks": [
                        {
                            "chunk_id": str(chunk["chunk_id"]),
                            "text": chunk["text"],
                        }
                        for chunk in group
                    ],
                },
                ensure_ascii=False,
            )
            parsed = self._call_model(_MAP_SYSTEM_PROMPT, payload, _MapOutput)
            for finding in parsed["findings"]:
                finding["evidence_chunk_ids"] = self._validate_ids(
                    finding.get("evidence_chunk_ids", []), metadata_by_id, str(chunk["document_id"] if False else document_id)
                )
                if finding["evidence_chunk_ids"]:
                    intermediate_findings.append(finding)
            all_limitations.extend(str(item).strip() for item in parsed["limitations"] if str(item).strip())

        final_payload = self._reduce_intermediate(intermediate_findings, style)
        reduction_level_count, reduction_groups_used = final_payload
        final = reduction_groups_used

        finding_models = self._validated_findings(final["findings"], metadata_by_id, document_id)
        limitations = self._deduplicate(all_limitations + final.get("limitations", []))
        return DocumentSummaryResponse(
            document_id=document_id,
            style=style,
            executive_summary=final["executive_summary"].strip(),
            findings=finding_models,
            limitations=limitations,
            map_group_count=len(groups),
            reduction_level_count=reduction_level_count,
        )

    def _group_chunks(self, chunks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        units: list[dict[str, str]] = []
        for chunk in chunks:
            chunk_id = str(chunk.get("id") or chunk.get("chunk_id") or "")
            text = str(chunk.get("content") or "").strip()
            if len(text) <= self.map_max_chars:
                units.append({"chunk_id": chunk_id, "text": text})
                continue
            start = 0
            while start < len(text):
                units.append({"chunk_id": chunk_id, "text": text[start:start + self.map_max_chars]})
                start += self.map_max_chars

        groups: list[list[dict[str, str]]] = []
        current: list[dict[str, str]] = []
        current_chars = 0
        for unit in units:
            unit_chars = len(unit["text"])
            if current and current_chars + unit_chars > self.map_max_chars:
                groups.append(current)
                current = []
                current_chars = 0
            current.append(unit)
            current_chars += unit_chars
        if current:
            groups.append(current)
        return groups

    def _call_model(self, system_prompt: str, user_payload: str, model_type: type[BaseModel]) -> dict[str, Any]:
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_payload}]
        raw = ""
        for attempt in range(2):
            try:
                raw = self.client.complete(messages)
                break
            except AnswerClientError as exc:
                if attempt == 1:
                    raise SummarizationError("The answer provider request failed.") from exc
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if len(lines) > 2 else lines)
        try:
            parsed = model_type.model_validate_json(cleaned)
            return parsed.model_dump()
        except (json.JSONDecodeError, ValidationError) as exc:
            raise SummarizationError("The answer provider returned malformed structured output.") from exc

    def _validate_ids(
        self,
        ids: list[str],
        authorized: dict[str, dict[str, Any]],
        document_id: str,
    ) -> list[str]:
        validated: list[str] = []
        for raw_id in ids:
            chunk_id = str(raw_id)
            chunk = authorized.get(chunk_id)
            if chunk is None or str(chunk.get("document_id", document_id)) != document_id:
                raise EvidenceValidationError("Model returned an unknown or unauthorized evidence chunk ID.")
            if chunk_id not in validated:
                validated.append(chunk_id)
        return validated

    def _reduce_intermediate(
        self,
        findings: list[dict[str, Any]],
        style: str,
    ) -> tuple[int, dict[str, Any]]:
        payload_items = findings
        levels = 0
        while True:
            serialized = json.dumps(payload_items, ensure_ascii=False)
            if len(serialized) <= self.reduce_max_chars:
                user_payload = json.dumps({"style": style, "intermediate_findings": payload_items}, ensure_ascii=False)
                final = self._call_model(_REDUCE_SYSTEM_PROMPT, user_payload, _ReduceOutput)
                return levels, final
            if levels >= self.max_reduction_levels:
                raise SummarizationError("The intermediate findings exceed the configured reduction budget.")

            groups: list[list[dict[str, Any]]] = []
            current: list[dict[str, Any]] = []
            current_chars = 0
            for finding in payload_items:
                item_chars = len(json.dumps(finding, ensure_ascii=False))
                if current and current_chars + item_chars > self.reduce_max_chars:
                    groups.append(current)
                    current = []
                    current_chars = 0
                current.append(finding)
                current_chars += item_chars
            if current:
                groups.append(current)

            next_items: list[dict[str, Any]] = []
            for group in groups:
                user_payload = json.dumps({"style": style, "intermediate_findings": group}, ensure_ascii=False)
                reduced = self._call_model(_REDUCE_SYSTEM_PROMPT, user_payload, _ReduceOutput)
                for finding in reduced["findings"]:
                    if finding.get("evidence_chunk_ids"):
                        next_items.append(finding)
                for limitation in reduced["limitations"]:
                    next_items.append({"text": "Limitations: " + str(limitation), "category": "qualification", "evidence_chunk_ids": []})
            payload_items = [item for item in next_items if item.get("evidence_chunk_ids")]
            levels += 1

    def _validated_findings(
        self,
        raw_findings: list[dict[str, Any]],
        metadata_by_id: dict[str, dict[str, Any]],
        document_id: str,
    ) -> list[SummaryFinding]:
        findings: list[SummaryFinding] = []
        for raw in raw_findings:
            ids = self._validate_ids(raw.get("evidence_chunk_ids", []), metadata_by_id, document_id)
            if not ids:
                continue
            evidence: list[EvidenceReference] = []
            for chunk_id in ids:
                chunk = metadata_by_id[chunk_id]
                evidence.append(EvidenceReference(
                    chunk_id=chunk_id,
                    page_number=chunk.get("page_number"),
                    page_start=chunk.get("page_start"),
                    page_end=chunk.get("page_end"),
                    section_title=chunk.get("section_title"),
                ))
            findings.append(SummaryFinding(text=raw["text"].strip(), category=raw.get("category", "main_point"), evidence=evidence))
        return findings

    @staticmethod
    def _deduplicate(items: list[str]) -> list[str]:
        output: list[str] = []
        for item in items:
            if item and item not in output:
                output.append(item)
        return output
