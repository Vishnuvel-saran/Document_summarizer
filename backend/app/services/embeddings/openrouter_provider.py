from __future__ import annotations

import math
from typing import Any

import tiktoken
from langchain_openai import OpenAIEmbeddings


class EmbeddingProviderError(RuntimeError):
    """Sanitized embedding-provider failure."""


class OpenRouterEmbeddingProvider:
    max_input_tokens = 8192
    base_url = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        *,
        api_key: str | None,
        model_id: str = "openai/text-embedding-3-small",
        dimension: int = 1536,
        batch_size: int = 32,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        embedding_client: Any | None = None,
    ) -> None:
        if dimension <= 0:
            raise ValueError("Embedding dimension must be positive.")
        if batch_size <= 0:
            raise ValueError("Embedding batch size must be positive.")
        if timeout_seconds <= 0:
            raise ValueError("Embedding timeout must be positive.")
        if not 0 <= max_retries <= 5:
            raise ValueError("Embedding retries must be between zero and five.")
        if embedding_client is None and not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is required for OpenRouter embeddings."
            )

        self._model_id = model_id
        self._dimension = dimension
        self.batch_size = batch_size
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.embeddings = embedding_client or OpenAIEmbeddings(
            model=model_id,
            api_key=api_key,
            base_url=self.base_url,
            chunk_size=batch_size,
            request_timeout=timeout_seconds,
            max_retries=max_retries,
            check_embedding_ctx_length=False,
            model_kwargs={"encoding_format": "float"},
        )

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_id(self) -> str:
        return self._model_id

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(item, str) or not item.strip() for item in texts):
            raise ValueError("Embedding inputs must be non-empty text strings.")
        if any(
            len(self.encoding.encode(item)) > self.max_input_tokens for item in texts
        ):
            raise ValueError("Embedding input exceeds the 8192-token model limit.")

        vectors: list[list[float]] = []
        for offset in range(0, len(texts), self.batch_size):
            batch = texts[offset : offset + self.batch_size]
            try:
                batch_vectors = self.embeddings.embed_documents(batch)
            except Exception as exc:
                raise EmbeddingProviderError(
                    "The OpenRouter embedding request failed."
                ) from exc

            if not isinstance(batch_vectors, list) or len(batch_vectors) != len(batch):
                raise EmbeddingProviderError(
                    "The embedding provider returned an unexpected vector count."
                )
            for vector in batch_vectors:
                if not isinstance(vector, list) or len(vector) != self.dimension:
                    raise EmbeddingProviderError(
                        "The embedding provider returned an invalid vector dimension."
                    )
                if any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    for value in vector
                ):
                    raise EmbeddingProviderError(
                        "The embedding provider returned malformed vector values."
                    )
                vectors.append([float(value) for value in vector])

        return vectors
