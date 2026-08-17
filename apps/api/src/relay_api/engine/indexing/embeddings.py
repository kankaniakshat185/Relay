"""Thin wrapper around the OpenAI embeddings call (ADR 0006). Kept
separate from `service.py` so the batching/API-call logic is one thing to
mock in tests, rather than reaching into `service.py`'s DB logic."""

from openai import AsyncOpenAI

from relay_api.core.config import get_settings

_MAX_CHARS_PER_ITEM = 8000
"""Rough guard against a single item's text blowing the model's token
limit — text-embedding-3-small's real limit is ~8191 tokens, this is a
conservative character-based approximation, not an exact token count."""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Returns one embedding vector per input text, same order. Empty
    input returns an empty list without making an API call."""
    if not texts:
        return []

    settings = get_settings()
    truncated = [t[:_MAX_CHARS_PER_ITEM] for t in texts]

    response = await _client().embeddings.create(model=settings.embedding_model, input=truncated)
    return [item.embedding for item in response.data]
