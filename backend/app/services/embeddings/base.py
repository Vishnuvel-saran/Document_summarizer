from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    @property
    def dimension(self) -> int: ...

    @property
    def model_id(self) -> str: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
