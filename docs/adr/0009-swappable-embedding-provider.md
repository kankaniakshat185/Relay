# ADR 0009: Embedding provider is a server-wide setting, not per-request BYOK

**Status:** Accepted — post-Phase 1

## What

`engine/indexing/embeddings.py` dispatches to one of two providers —
OpenAI (`text-embedding-3-small`, the ADR 0006 default) or Gemini
(`gemini-embedding-001`) — based on `settings.embedding_provider`
(`"openai"` or `"gemini"`). Both are configured to output the same
`EMBEDDING_DIMENSIONS` (1536), so the `ingested_items.embedding`
column/HNSW index never changes shape when switching. This is a single
env var (`EMBEDDING_PROVIDER`), not a per-request choice.

## Why

Real-world trigger: testing hit OpenAI's `insufficient_quota` — no
billing configured on the account — which blocks embeddings entirely,
since every search and every indexing run needs one unconditionally
(unlike synthesis, which raw mode skips outright, ADR 0008). Gemini's
free tier (an AI Studio key, no credit card required) is a genuine
zero-cost way to keep testing while OpenAI billing gets sorted.

**Why this is a server-wide setting, not BYOK like synthesis:** BYOK
(ADR 0008) works for synthesis because it's optional and per-request —
a user who wants AI Summary brings their own key for that one call.
Embeddings have no such opt-out: they're load-bearing infra for every
search and every indexing run, for every user, all the time. Making that
per-request would mean either asking every user for an embedding-provider
key before they can search at all (bad UX for the thing that's supposed
to be free), or maintaining two live embedding spaces simultaneously
(meaningless — vectors from different models/dimensions aren't
comparable, so mixing them per-request breaks retrieval, not just cost).
A single server-side setting is the only architecture that keeps "search
works for free, unconditionally" true.

**Why matching dimensionality matters:** Gemini's embedding model supports
Matryoshka-style output truncation via `output_dimensionality`, so
requesting 1536 dimensions specifically means switching providers is a
config flip, not a schema migration — no Alembic revision, no HNSW index
rebuild, no downtime.

**What switching does NOT do:** make old and new embeddings comparable.
A vector from OpenAI and a vector from Gemini occupy different learned
spaces even at identical dimensionality — cosine similarity between them
is meaningless. Existing rows keep whatever embedding they already have;
only rows with `embedding IS NULL` get picked up by the next indexing
pass under the new provider (same mechanism `engine/ingestion/service.py`
already uses when an item's content changes). Switching providers after
real data is already indexed means clearing `embedding`/`search_vector`
on existing rows to force a full re-embed — not needed here, since at the
time of this switch the OpenAI quota error meant nothing had successfully
embedded yet.

## How

- `core/config.py` — `embedding_provider: Literal["openai", "gemini"]`
  (default `"openai"`, matching ADR 0006), `gemini_api_key`,
  `gemini_embedding_model` (default `"gemini-embedding-001"`).
- `engine/indexing/embeddings.py` — `_embed_openai`/`_embed_gemini`, both
  wrapping their SDK's own exceptions into the same
  `EmbeddingUnavailableError` (see the `main.py` exception handler this
  feeds — a failure here is "search is down", not something to silently
  retry or fall back from). `embed_texts()` is the only public entry
  point; callers never know or care which provider actually ran.
- Flipping back to OpenAI once billing is active: set
  `EMBEDDING_PROVIDER=openai` (or unset it, since that's the default) and
  restart. No other code change.
