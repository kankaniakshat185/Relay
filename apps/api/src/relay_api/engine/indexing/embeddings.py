"""Embedding calls (ADR 0006) — provider-switchable (ADR 0009), unlike
synthesis's per-request BYOK (ADR 0008). Embeddings are unconditional core
infra: every search and every indexing run needs one, so which provider
produces them is a server-wide setting (`settings.embedding_provider`),
not something a request chooses.

Both providers are made to output the same `EMBEDDING_DIMENSIONS` (1536)
so the `ingested_items.embedding` column/HNSW index never needs to change
shape when switching — Gemini's embedding model supports Matryoshka
truncation via `output_dimensionality` specifically so this lines up.

Switching providers does NOT make old and new embeddings comparable —
they're different vector spaces even at the same dimensionality. Existing
rows keep whatever embedding they already have; only re-indexed rows
(`embedding IS NULL`) pick up the new provider. If you switch providers
after already indexing real data, clear `embedding`/`search_vector` on
existing rows to force a full re-embed — see `engine/ingestion/service.py`
for how content changes already do this per-row.
"""

import openai
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from openai import AsyncOpenAI

from relay_api.core.config import get_settings
from relay_api.engine.ingestion.models import EMBEDDING_DIMENSIONS

_MAX_CHARS_PER_ITEM = 8000
"""Rough guard against a single item's text blowing the model's token
limit — text-embedding-3-small's real limit is ~8191 tokens, this is a
conservative character-based approximation, not an exact token count."""

_MAX_BATCH_SIZE = 96
"""Found the hard way: Gemini's batch embed endpoint hard-caps at 100
requests per call, and a single GitHub indexing pass alone (10 repos ×
up to 20 PRs + 20 commits each) can produce ~400 items — comfortably over
that. OpenAI's own limit is much higher (2048), which is why this never
surfaced before switching providers. Chunking here, once, generically,
rather than a Gemini-specific patch — safe for any provider's limit,
including ones smaller than this."""


class EmbeddingUnavailableError(Exception):
    """The embeddings call failed — quota, billing, or a transient
    provider error. Search and indexing both depend on this unconditionally
    (there's no raw-mode-skips-it option, ADR 0008 only exempts synthesis),
    so this is a "the feature is down" error, not something to retry
    silently or fall back from."""


async def _embed_openai(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.embeddings.create(model=settings.embedding_model, input=texts)
    except openai.APIError as exc:
        raise EmbeddingUnavailableError(str(exc)) from exc

    return [item.embedding for item in response.data]


async def _embed_gemini(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)
    try:
        response = await client.aio.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=texts,
            config=genai_types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
        )
    except genai_errors.APIError as exc:
        raise EmbeddingUnavailableError(str(exc)) from exc

    if response.embeddings is None:
        raise EmbeddingUnavailableError("Gemini returned no embeddings for the request")
    return [list(embedding.values or []) for embedding in response.embeddings]


_PROVIDERS = {"openai": _embed_openai, "gemini": _embed_gemini}


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Returns one embedding vector per input text, same order. Empty
    input returns an empty list without making an API call."""
    if not texts:
        return []

    truncated = [t[:_MAX_CHARS_PER_ITEM] for t in texts]
    provider = _PROVIDERS[get_settings().embedding_provider]

    results: list[list[float]] = []
    for start in range(0, len(truncated), _MAX_BATCH_SIZE):
        batch = truncated[start : start + _MAX_BATCH_SIZE]
        results.extend(await provider(batch))
    return results
