"""OpenRouter LLM client for answer generation.

Uses the openai Python SDK pointed at the OpenRouter base URL so we can reuse
the same integration pattern as the embedding client.  A separate API key
(ANSWER_API_KEY) is used so usage can be tracked and rotated independently.
"""

from __future__ import annotations

from openai import OpenAI


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class AnswerClientError(RuntimeError):
    """Sanitised failure from the answer-generation provider."""


class OpenRouterAnswerClient:
    """Thin wrapper around the OpenAI-compatible OpenRouter chat endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "google/gemma-4-26b-a4b-it:free",
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        # Injected in tests to avoid real HTTP calls.
        _client: OpenAI | None = None,
    ) -> None:
        if not api_key and _client is None:
            raise ValueError("ANSWER_API_KEY is required for answer generation.")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive.")

        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        self._client = _client or OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    def complete(self, messages: list[dict]) -> str:
        """Send a list of chat messages and return the assistant reply text."""
        if not messages:
            raise ValueError("messages must not be empty.")
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        except Exception as exc:
            raise AnswerClientError(
                "The answer provider request failed."
            ) from exc

        choice = response.choices[0] if response.choices else None
        if choice is None or choice.message is None or choice.message.content is None:
            raise AnswerClientError("The answer provider returned an empty response.")

        return choice.message.content.strip()

