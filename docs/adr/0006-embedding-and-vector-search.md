# ADR 0006: pgvector on Neon + OpenAI text-embedding-3-small

**Status:** Accepted — pre-Phase 1

## What

`engine/indexing` stores embeddings in the existing Neon Postgres via the
`pgvector` extension — no separate vector database. Embeddings are produced
by OpenAI's `text-embedding-3-small` via API call, not a self-hosted model.
Semantic (vector) search runs alongside Postgres full-text search
(`tsvector`/GIN) on the same rows, not as a separate system.

## Why

**pgvector over a dedicated vector DB (Pinecone/Weaviate/Qdrant):**
`engine/indexing`'s actual job isn't "find similar vectors" in isolation —
it's "find similar vectors *within* a structured filter" (this provider,
this time range, this entity), because that's what the correlation engine
(ADR 0005) needs to hand `engine/ranking`. With pgvector, that's one SQL
query: structured `WHERE` clauses plus `ORDER BY embedding <=> query_embedding`.
With a separate vector DB, the same operation means running two queries
against two systems and joining the results in application code — more
moving parts for the same outcome, and a second data store to keep in sync
with ingestion. This also matches a pattern already set elsewhere in the
project: skip infrastructure that isn't earning its place yet (no
Turborepo, no Neon-branch-per-PR in CI — see plan.md §9). Neon supports
`pgvector` natively, so this doesn't even add a new managed service.

**Hybrid keyword + embedding, not embedding-only:** a lot of the queries
this engine needs to answer are exact-match-friendly — ticket IDs, function
names, error strings, someone's name — where keyword search wins outright.
Others ("the bug Priya mentioned last week") genuinely need semantic
similarity. Postgres full-text search columns live on the same rows as the
embedding column, so this is additional indexes, not additional
infrastructure.

**OpenAI `text-embedding-3-small` over a self-hosted model
(BGE/E5/sentence-transformers):** a self-hosted embedding model means
managing model weights, inference latency, and CPU/GPU cost as a new
concern inside `engine/indexing` — which should stay an orchestration
layer, not grow into an ML-serving component. An API call keeps it
consistent with how GitHub/Slack/Jira are already integrated (all API
calls). Cost at this project's scale is negligible (~$0.02 per million
tokens), and `text-embedding-3-small`'s quality is sufficient because
embeddings only need to get candidates into the right neighborhood —
`engine/ranking` (Phase 2, differential-tested) is where actual relevance
scoring happens, not here.

**Why this isn't a `engine/ranking` differential-testing candidate:**
embedding model choice determines what gets *retrieved*; ranking strategy
determines how retrieved candidates get *ordered*. They're different
layers — conflating them would blur the differential-testing scope plan.md
§6 already draws around `engine/ranking` specifically.

## How

- Neon Postgres: enable the `pgvector` extension via an Alembic migration
  in Phase 1, alongside the ingestion tables `engine/ingestion` needs.
- `engine/indexing` calls OpenAI's embeddings endpoint at ingestion time
  (not query time only) and stores the resulting vector alongside each
  normalized item.
- Query path: `engine/indexing` runs a combined keyword + vector query
  scoped by the structured filters (provider, time range, entity) the
  calling feature (`context_search`, `archaeology`, `who_to_ask`) supplies;
  `engine/ranking` orders the combined candidate set.
- If embedding provider ever changes, existing vectors need re-embedding —
  vectors from different models aren't comparable. That's a migration
  concern for whenever this decision gets revisited, not a Phase 1 problem.
