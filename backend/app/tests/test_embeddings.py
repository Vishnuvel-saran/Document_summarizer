from unittest.mock import MagicMock, patch

import pytest

from app.services.embeddings.openrouter_provider import (
    EmbeddingProviderError,
    OpenRouterEmbeddingProvider,
)


def test_embedding_provider_batches_and_preserves_input_order() -> None:
    embeddings = MagicMock()
    embeddings.embed_documents.side_effect = [
        [[1.0, 1.0], [2.0, 2.0]],
        [[3.0, 3.0]],
    ]
    provider = OpenRouterEmbeddingProvider(
        api_key=None, dimension=2, batch_size=2, embedding_client=embeddings
    )

    vectors = provider.embed_documents(["first", "second", "third"])

    assert vectors == [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]
    assert embeddings.embed_documents.call_count == 2
    assert embeddings.embed_documents.call_args_list[0].args[0] == ["first", "second"]
    assert provider.model_id == "openai/text-embedding-3-small"
    assert provider.dimension == 2


def test_embedding_provider_rejects_wrong_vector_count() -> None:
    embeddings = MagicMock()
    embeddings.embed_documents.return_value = [[1.0, 1.0]]
    provider = OpenRouterEmbeddingProvider(
        api_key=None, dimension=2, embedding_client=embeddings
    )

    with pytest.raises(EmbeddingProviderError, match="vector count"):
        provider.embed_documents(["one", "two"])


def test_embedding_provider_rejects_wrong_dimension_and_non_finite_values() -> None:
    embeddings = MagicMock()
    embeddings.embed_documents.return_value = [[1.0]]
    provider = OpenRouterEmbeddingProvider(
        api_key=None, dimension=2, embedding_client=embeddings
    )
    with pytest.raises(EmbeddingProviderError, match="dimension"):
        provider.embed_documents(["one"])

    embeddings.embed_documents.return_value = [[float("nan"), 1.0]]
    with pytest.raises(EmbeddingProviderError, match="malformed"):
        provider.embed_documents(["one"])


def test_langchain_adapter_uses_openrouter_endpoint_and_exact_model() -> None:
    with patch(
        "app.services.embeddings.openrouter_provider.OpenAIEmbeddings"
    ) as langchain_embeddings:
        OpenRouterEmbeddingProvider(
            api_key="test-key",
            model_id="openai/text-embedding-3-small",
            dimension=1536,
            batch_size=32,
            timeout_seconds=12,
            max_retries=1,
        )

    kwargs = langchain_embeddings.call_args.kwargs
    assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
    assert kwargs["model"] == "openai/text-embedding-3-small"
    assert "dimensions" not in kwargs
    assert kwargs["chunk_size"] == 32
    assert kwargs["max_retries"] == 1
    assert kwargs["request_timeout"] == 12
    assert kwargs["check_embedding_ctx_length"] is False
    assert kwargs["model_kwargs"]["encoding_format"] == "float"


def test_embedding_provider_rejects_empty_and_oversized_inputs() -> None:
    embeddings = MagicMock()
    provider = OpenRouterEmbeddingProvider(
        api_key=None, dimension=2, embedding_client=embeddings
    )

    with pytest.raises(ValueError, match="non-empty"):
        provider.embed_documents(["  "])
    with pytest.raises(ValueError, match="8192-token"):
        provider.embed_documents(["token " * 8200])
    embeddings.embed_documents.assert_not_called()


def test_embedding_provider_sanitizes_provider_errors() -> None:
    embeddings = MagicMock()
    embeddings.embed_documents.side_effect = RuntimeError("sensitive provider detail")
    provider = OpenRouterEmbeddingProvider(
        api_key=None, dimension=2, embedding_client=embeddings
    )

    with pytest.raises(EmbeddingProviderError, match="request failed") as error:
        provider.embed_documents(["one"])

    assert "sensitive provider detail" not in str(error.value)
