"""Found the hard way: an unhandled OpenAI error here (quota, billing,
outage) surfaced as a raw 500 to every search regardless of mode, since
embeddings aren't optional the way LLM synthesis is (ADR 0006/0008). Also
covers the provider switch (ADR 0009) — dispatch, and that both providers
map their own SDK errors to the same `EmbeddingUnavailableError`.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import openai
import pytest
from google.genai import errors as genai_errors

from relay_api.core.config import get_settings
from relay_api.engine.indexing import embeddings


async def test_empty_input_returns_empty_without_calling_the_api() -> None:
    with patch.object(embeddings, "AsyncOpenAI") as mock_cls:
        result = await embeddings.embed_texts([])

    assert result == []
    mock_cls.assert_not_called()


async def test_openai_provider_is_used_when_configured() -> None:
    # Explicitly pinned, not relying on the class default — a developer's
    # local .env (which pydantic-settings reads relative to cwd) can set
    # EMBEDDING_PROVIDER=gemini for their own testing, and this test must
    # not be fragile to that.
    with (
        patch.object(get_settings(), "embedding_provider", "openai"),
        patch.object(embeddings, "AsyncOpenAI") as mock_cls,
    ):
        mock_cls.return_value.embeddings.create = AsyncMock(
            return_value=SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])
        )
        await embeddings.embed_texts(["hello"])

    mock_cls.assert_called_once_with(api_key=get_settings().openai_api_key)


async def test_openai_quota_error_is_wrapped_as_embedding_unavailable() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    quota_error = openai.RateLimitError(
        "insufficient_quota", response=httpx.Response(429, request=request), body=None
    )

    with (
        patch.object(get_settings(), "embedding_provider", "openai"),
        patch.object(embeddings, "AsyncOpenAI") as mock_cls,
    ):
        mock_cls.return_value.embeddings.create = AsyncMock(side_effect=quota_error)

        with pytest.raises(embeddings.EmbeddingUnavailableError):
            await embeddings.embed_texts(["some query"])


async def test_gemini_provider_returns_vectors_at_configured_dimensions() -> None:
    fake_embedding = SimpleNamespace(values=[0.1] * embeddings.EMBEDDING_DIMENSIONS)
    fake_response = SimpleNamespace(embeddings=[fake_embedding])

    with (
        patch.object(get_settings(), "embedding_provider", "gemini"),
        patch.object(embeddings.genai, "Client") as mock_cls,
    ):
        mock_cls.return_value.aio.models.embed_content = AsyncMock(return_value=fake_response)

        result = await embeddings.embed_texts(["hello"])

        call_kwargs = mock_cls.return_value.aio.models.embed_content.call_args.kwargs
        assert call_kwargs["config"].output_dimensionality == embeddings.EMBEDDING_DIMENSIONS

    assert result == [[0.1] * embeddings.EMBEDDING_DIMENSIONS]


async def test_gemini_api_error_is_wrapped_as_embedding_unavailable() -> None:
    error = genai_errors.ClientError(401, {"error": {"message": "invalid API key"}})

    with (
        patch.object(get_settings(), "embedding_provider", "gemini"),
        patch.object(embeddings.genai, "Client") as mock_cls,
    ):
        mock_cls.return_value.aio.models.embed_content = AsyncMock(side_effect=error)

        with pytest.raises(embeddings.EmbeddingUnavailableError):
            await embeddings.embed_texts(["some query"])


async def test_large_input_is_chunked_into_multiple_provider_calls() -> None:
    """Real bug, real data: a single GitHub indexing pass produced ~150
    items in one call, and Gemini's batch endpoint rejects anything over
    100 outright — this must chunk regardless of which provider is active."""
    texts = [f"item {i}" for i in range(150)]
    batch_sizes: list[int] = []

    async def fake_embed(batch: list[str]) -> list[list[float]]:
        batch_sizes.append(len(batch))
        return [[0.1] for _ in batch]

    with (
        patch.object(get_settings(), "embedding_provider", "openai"),
        patch.dict(embeddings._PROVIDERS, {"openai": fake_embed}),
    ):
        result = await embeddings.embed_texts(texts)

    assert len(result) == 150
    assert batch_sizes == [96, 54]  # two calls, neither over the 96-item cap
