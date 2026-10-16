"""Unit tests for the grounded answer generation service.

All tests are fully offline — the OpenRouter LLM client is replaced with a
controllable fake so no network calls are made.
"""

from __future__ import annotations

import pytest

from app.schemas.retrieval import RetrievalResult
from app.services.answer.client import AnswerClientError, OpenRouterAnswerClient
from app.services.answer.service import (
    AnswerService,
    _build_evidence_block,
    _extract_citations,
    _validate_and_strip_citations,
)


# ---------------------------------------------------------------------------
# Helper factory
# ---------------------------------------------------------------------------

def _chunk(chunk_id: str, content: str, page: int = 1) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id="doc-1",
        content=content,
        page_number=page,
        page_start=page,
        page_end=page,
        section_title="Test Section",
        block_type="paragraph",
        source_block_indices=[0],
        source_metadata={},
        rank=1,
        retrieval_mode="hybrid",
        rrf_score=0.03,
    )


class FakeLLMClient:
    """Controllable stand-in for OpenRouterAnswerClient."""

    def __init__(self, reply: str = "", raise_error: bool = False) -> None:
        self.reply = reply
        self.raise_error = raise_error
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict]) -> str:
        self.calls.append(messages)
        if self.raise_error:
            raise AnswerClientError("Provider offline.")
        return self.reply


# ---------------------------------------------------------------------------
# _build_evidence_block
# ---------------------------------------------------------------------------

def test_build_evidence_block_formats_chunk_ids_and_location() -> None:
    chunks = [
        _chunk("abc-123", "The notice period is 30 days.", page=4),
        _chunk("def-456", "Invoices must be paid within 14 days.", page=7),
    ]
    block = _build_evidence_block(chunks)

    assert "[abc-123]" in block
    assert "page 4" in block
    assert "30 days" in block
    assert "[def-456]" in block
    assert "page 7" in block


def test_build_evidence_block_returns_empty_string_for_no_chunks() -> None:
    assert _build_evidence_block([]) == ""


# ---------------------------------------------------------------------------
# _extract_citations
# ---------------------------------------------------------------------------

def test_extract_citations_finds_all_bracketed_ids() -> None:
    text = "The notice period is 30 days [abc-123]. Invoices [def-456] are also mentioned."
    assert _extract_citations(text) == {"abc-123", "def-456"}


def test_extract_citations_returns_empty_set_for_no_citations() -> None:
    assert _extract_citations("No citations here.") == set()


# ---------------------------------------------------------------------------
# _validate_and_strip_citations
# ---------------------------------------------------------------------------

def test_validate_strips_invalid_citations_and_keeps_valid() -> None:
    valid_ids = {"abc-123", "def-456"}
    text = "Notice period is 30 days [abc-123]. See also [fake-id] and [def-456]."

    clean, invalid = _validate_and_strip_citations(text, valid_ids)

    assert "[abc-123]" in clean
    assert "[def-456]" in clean
    assert "[fake-id]" not in clean
    assert invalid == ["fake-id"]


def test_validate_strips_nothing_when_all_citations_valid() -> None:
    valid_ids = {"c1", "c2"}
    text = "Statement [c1] and another [c2]."
    clean, invalid = _validate_and_strip_citations(text, valid_ids)
    assert clean == text
    assert invalid == []


def test_validate_strips_all_citations_when_none_valid() -> None:
    text = "Bad [x1] and [x2]."
    clean, invalid = _validate_and_strip_citations(text, set())
    assert "[x1]" not in clean
    assert "[x2]" not in clean
    assert set(invalid) == {"x1", "x2"}


# ---------------------------------------------------------------------------
# AnswerService
# ---------------------------------------------------------------------------

def test_answer_service_returns_clean_answer_with_cited_ids() -> None:
    chunks = [_chunk("c1", "30 days notice required.", page=2)]
    client = FakeLLMClient(reply="The notice period is 30 days [c1].")
    service = AnswerService(client)

    result = service.answer(query="What is the notice period?", chunks=chunks)

    assert result.answer == "The notice period is 30 days [c1]."
    assert result.cited_chunk_ids == ["c1"]
    assert result.invalid_citations == []
    assert result.has_evidence is True
    assert result.chunk_count == 1


def test_answer_service_strips_hallucinated_citation() -> None:
    chunks = [_chunk("real-id", "Some content.", page=1)]
    client = FakeLLMClient(reply="Answer [real-id] plus invented [ghost-id].")
    service = AnswerService(client)

    result = service.answer(query="Some question?", chunks=chunks)

    assert "[ghost-id]" not in result.answer
    assert "ghost-id" in result.invalid_citations
    assert result.cited_chunk_ids == ["real-id"]


def test_answer_service_handles_empty_chunks_without_error() -> None:
    client = FakeLLMClient(
        reply="The document does not provide sufficient evidence to answer this question."
    )
    service = AnswerService(client)

    result = service.answer(query="Anything?", chunks=[])

    assert result.has_evidence is False
    assert result.cited_chunk_ids == []
    assert result.chunk_count == 0


def test_answer_service_passes_system_and_user_messages_to_client() -> None:
    chunks = [_chunk("id-1", "Some text.")]
    client = FakeLLMClient(reply="Answer [id-1].")
    service = AnswerService(client)

    service.answer(query="Test query.", chunks=chunks)

    assert len(client.calls) == 1
    messages = client.calls[0]
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user"]
    assert "id-1" in messages[1]["content"]
    assert "Test query." in messages[1]["content"]


def test_answer_service_raises_on_blank_query() -> None:
    service = AnswerService(FakeLLMClient())
    with pytest.raises(ValueError, match="blank"):
        service.answer(query="   ", chunks=[])


def test_answer_service_propagates_client_error() -> None:
    chunks = [_chunk("c1", "Some content.")]
    client = FakeLLMClient(raise_error=True)
    service = AnswerService(client)

    with pytest.raises(AnswerClientError, match="Provider offline"):
        service.answer(query="What is the notice period?", chunks=chunks)


# ---------------------------------------------------------------------------
# OpenRouterAnswerClient
# ---------------------------------------------------------------------------

def test_answer_client_requires_api_key() -> None:
    with pytest.raises(ValueError, match="ANSWER_API_KEY"):
        OpenRouterAnswerClient(api_key="")


def test_answer_client_rejects_zero_max_tokens() -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        OpenRouterAnswerClient(api_key="key", max_tokens=0)


def test_answer_client_complete_calls_openai_and_returns_text() -> None:
    from unittest.mock import MagicMock

    mock_openai = MagicMock()
    choice = MagicMock()
    choice.message.content = "  Mocked reply.  "
    mock_openai.chat.completions.create.return_value.choices = [choice]

    client = OpenRouterAnswerClient(api_key="key", _client=mock_openai)
    result = client.complete([{"role": "user", "content": "Hello"}])

    assert result == "Mocked reply."
    mock_openai.chat.completions.create.assert_called_once()


def test_answer_client_raises_on_empty_response() -> None:
    from unittest.mock import MagicMock

    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value.choices = []

    client = OpenRouterAnswerClient(api_key="key", _client=mock_openai)
    with pytest.raises(AnswerClientError, match="empty response"):
        client.complete([{"role": "user", "content": "Hello"}])


def test_answer_client_wraps_provider_error() -> None:
    from unittest.mock import MagicMock

    mock_openai = MagicMock()
    mock_openai.chat.completions.create.side_effect = RuntimeError("Network error")

    client = OpenRouterAnswerClient(api_key="key", _client=mock_openai)
    with pytest.raises(AnswerClientError, match="request failed"):
        client.complete([{"role": "user", "content": "Hello"}])

