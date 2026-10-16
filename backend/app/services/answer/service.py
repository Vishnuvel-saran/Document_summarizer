"""Grounded answer generation service.

Takes a user question and a list of retrieved chunks, asks the LLM to answer
using only the provided evidence, and validates that every citation in the
model's answer corresponds to an actual retrieved chunk ID.

Design rules enforced here:
- The model is given only the retrieved chunks as its evidence — no wider
  context is injected.
- The model is instructed to cite by chunk ID, e.g. [chunk-uuid].
- If the retrieved evidence is insufficient the model should say so
  explicitly rather than speculating.
- After generation, citations are validated against the actual chunk IDs.
  A citation that does not match a retrieved chunk is flagged as invalid and
  stripped from the final answer.
"""

from __future__ import annotations

import re

from app.schemas.retrieval import RetrievalResult
from app.services.answer.client import OpenRouterAnswerClient

# Matches "[<some-uuid-or-id>]" citations embedded in model output.
_CITATION_RE = re.compile(r"\[([^\[\]]+)\]")

_SYSTEM_PROMPT = """\
You are a precise document analyst. You are given a question and a set of \
evidence chunks retrieved from a specific document. Your job is to answer the \
question using ONLY the provided evidence.

Rules:
1. Cite every piece of evidence you use by placing the chunk ID in square \
brackets immediately after the relevant statement, e.g. [chunk-abc123].
2. If the evidence does not contain enough information to answer the question, \
respond with exactly: "The document does not provide sufficient evidence to \
answer this question." Do NOT speculate or invent information.
3. Keep your answer concise and factual.
4. Do not repeat the question in your answer.
"""


def _build_evidence_block(chunks: list[RetrievalResult]) -> str:
    """Format retrieved chunks into an evidence block for the prompt."""
    lines: list[str] = []
    for chunk in chunks:
        location_parts: list[str] = []
        if chunk.page_number is not None:
            location_parts.append(f"page {chunk.page_number}")
        if chunk.section_title:
            location_parts.append(f"section '{chunk.section_title}'")
        location = ", ".join(location_parts) or "unknown location"
        lines.append(
            f"[{chunk.chunk_id}] ({location})\n{chunk.content.strip()}"
        )
    return "\n\n".join(lines)


def _extract_citations(text: str) -> set[str]:
    """Return all citation IDs found inside square brackets in *text*."""
    return {m.group(1) for m in _CITATION_RE.finditer(text)}


def _validate_and_strip_citations(
    answer: str,
    valid_ids: set[str],
) -> tuple[str, list[str]]:
    """
    Remove citations that don't reference an actual retrieved chunk.

    Returns the cleaned answer text and a list of invalid citation IDs that
    were detected and removed.
    """
    invalid: list[str] = []

    def _replace(match: re.Match) -> str:
        cited_id = match.group(1)
        if cited_id in valid_ids:
            return match.group(0)  # Keep valid citation
        invalid.append(cited_id)
        return ""  # Strip invalid citation

    cleaned = _CITATION_RE.sub(_replace, answer).strip()
    return cleaned, invalid


class AnswerService:
    """Generate grounded answers from retrieved evidence chunks."""

    def __init__(self, client: OpenRouterAnswerClient) -> None:
        self.client = client

    def answer(
        self,
        *,
        query: str,
        chunks: list[RetrievalResult],
    ) -> "AnsweredQuery":
        """
        Generate a grounded answer for *query* using *chunks* as evidence.

        Returns an ``AnsweredQuery`` with the answer text, validated citations,
        and any invalid citations that were stripped.
        """
        if not query.strip():
            raise ValueError("Query must not be blank.")

        # Even with zero chunks we still ask the model — it will correctly
        # report no evidence rather than hallucinating.
        valid_ids: set[str] = {chunk.chunk_id for chunk in chunks}

        evidence_block = _build_evidence_block(chunks) if chunks else "(No evidence retrieved)"

        user_message = (
            f"Evidence:\n\n{evidence_block}\n\n"
            f"Question: {query.strip()}"
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        raw_answer = self.client.complete(messages)

        # Validate citations: strip any that don't match a real chunk ID.
        clean_answer, invalid_citations = _validate_and_strip_citations(
            raw_answer, valid_ids
        )
        cited_ids = sorted(_extract_citations(clean_answer) & valid_ids)

        return AnsweredQuery(
            query=query,
            answer=clean_answer,
            cited_chunk_ids=cited_ids,
            invalid_citations=invalid_citations,
            chunk_count=len(chunks),
        )


class AnsweredQuery:
    """Result object returned by ``AnswerService.answer``."""

    def __init__(
        self,
        *,
        query: str,
        answer: str,
        cited_chunk_ids: list[str],
        invalid_citations: list[str],
        chunk_count: int,
    ) -> None:
        self.query = query
        self.answer = answer
        self.cited_chunk_ids = cited_chunk_ids
        self.invalid_citations = invalid_citations
        self.chunk_count = chunk_count

    @property
    def has_evidence(self) -> bool:
        """True when the answer cites at least one retrieved chunk."""
        return bool(self.cited_chunk_ids)

