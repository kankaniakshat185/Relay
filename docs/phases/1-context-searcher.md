# Phase 1 retro: Context Searcher (vertical slice)

**Shipped:** 2026-08-18

## What shipped

- **Connector data-access OAuth** for GitHub, Slack, Jira (ADR 0003) —
  distinct from login OAuth (Phase 0). Each provider's OAuth quirks handled
  on their own terms rather than forced into one generic flow: GitHub is
  the "normal" authorization-code exchange, Slack is a bot-token install
  flow (`oauth.v2.access`), Jira needs an extra `accessible-resources`
  round trip to resolve a cloud id. `connector_credentials` tokens are
  Fernet-encrypted at rest (`connectors/encryption.py`), never plaintext.
- **Read-only connector clients + normalizers** — GitHub PRs, Slack
  messages, Jira issues (with ADF-to-text flattening for descriptions),
  each converted into the shared `NormalizedItem` shape (ADR 0005's "one
  engine" contract, made concrete).
- **The correlation engine's first two pieces**: `engine/ingestion`
  (upsert with dedupe — re-ingesting unchanged content is a no-op, changed
  content clears stale embedding/search_vector so it gets re-indexed) and
  `engine/indexing` (pgvector + Postgres full-text search, hybrid keyword +
  vector search with a fixed-weight combination — see ADR 0006 and the
  note below on why ranking sophistication is deliberately NOT here).
- **Celery indexing job** — fires after a connector finishes connecting,
  runs fetch → normalize → ingest → index for that provider.
- **Context Searcher** (`features/context_search`) — retrieves via the
  engine, synthesizes a source-attributed answer via OpenAI structured
  output (ADR 0007). The model returns which candidate indices it actually
  used, not free-form prose scraped for citations, so the frontend renders
  real retrieved items, not the model's own formatting.
- **Frontend**: Connections page (per-provider connect/disconnect,
  redirects into the backend OAuth flow) and Search page (query → answer +
  source list), both wired against the real backend.
- **Visual design pass**: at the user's direction, the dashboard (login,
  nav, home, Connections, Search) was restyled to a bold serif/red-block
  editorial look, replacing the plain Tailwind default from Phase 0 —
  `Fraunces` for display type, red as the brand token, structured card
  grids. Scoped to the dashboard shell + Phase 1 pages; Phase 2+ pages
  inherit the same tokens.
- 2 new ADRs (0006 embeddings/vector search, 0007 synthesis LLM), both
  decided via direct questions back to the user rather than picked
  unilaterally — see plan.md §9 resolution log.

## What got cut or simplified within this phase

- **One connected account per provider per user** — same simplification as
  the login/connector split in ADR 0003, now extended to connectors
  themselves. A user with two GitHub orgs or two Jira sites only gets the
  first. Documented in `connectors/models.py` and `connectors/jira/provider.py`,
  not accidental.
- **GitHub's OAuth scope (`repo`) is broader than Relay's actual read-only
  usage** — there's no narrower classic-OAuth scope for private-repo read
  access. Noted in `connectors/github/provider.py` as a real limitation, not
  glossed over; a GitHub App with fine-grained permissions would close this
  gap if it ever matters.
- **No token refresh flow** — Slack bot tokens don't expire under the
  classic install flow, but GitHub/Jira tokens that do expire have no
  refresh handling yet. Fine for a demo; a real gap before this ships
  anywhere durable.
- **Search ranking is a fixed-weight hybrid score (0.4 keyword / 0.6
  vector), not a tuned or compared strategy.** This is intentional, not
  unfinished — `engine/ranking` (Phase 2) is where competing strategies get
  built and differential-tested (plan.md §6); Phase 1's job was proving the
  retrieval path works, not optimizing it.
- **No ingestion/indexing progress surfaced to the user** — the Celery job
  runs fully async with no polling or status UI; a user who connects
  GitHub and immediately searches may get an empty result set with no
  explanation that indexing is still running. Worth a small status
  indicator in Phase 2, not addressed now.
- **Errors in the OAuth exchange or indexing job aren't surfaced to the
  user** — they log server-side (structured JSON, per Phase 0) but a failed
  connector callback or a failed indexing run currently just... fails
  quietly from the user's point of view. Same category as the above.

## What was harder than expected

- **pgvector + Alembic autogenerate doesn't import its own type.**
  Autogenerate renders `pgvector.sqlalchemy.vector.VECTOR(...)` in the
  migration file but never adds the `import pgvector.sqlalchemy` line —
  pgvector has no first-party Alembic integration. Caught by actually
  running the migration against a real `pgvector/pgvector:pg16` container
  before trusting it (same discipline as Phase 0's migration testing),
  not by reading the generated file and assuming it was correct.
- **The module-level async engine singleton (`core/db.py`) doesn't survive
  pytest-asyncio's default per-test event loop.** Fine in Phase 0 (no
  DB-touching async tests existed yet); broke on the second integration
  test in this phase with an opaque "Future attached to a different loop"
  error. Fixed by pinning `asyncio_default_fixture_loop_scope` and
  `asyncio_default_test_loop_scope` to `"session"` — matching how the app
  actually runs in production (one loop for the process's whole lifetime),
  not a workaround.
- **`pytest-env`'s default entries silently override real environment
  variables**, including CI's job-level `env:` block. Only surfaced because
  local verification connected to a stray Postgres container from an
  unrelated project on the same port. Fixed with the `D:` prefix (fallback
  default, doesn't clobber an already-set var) — a real fix for CI
  correctness, not just a local dev convenience.
- **OpenAI's SDK is strictly typed against a large union of TypedDicts**
  for `messages` and `response_format`; a plain `dict` doesn't satisfy the
  overloads under `mypy --strict`. Fixed by typing against
  `ChatCompletionMessageParam` and `ResponseFormatJSONSchema` explicitly
  rather than suppressing the error.

## Open items carried forward

- Whether Neon branch-per-PR gets adopted later for CI (unchanged from
  Phase 0 — still Dockerized Postgres, now `pgvector/pgvector:pg16`
  specifically; revisit only if it causes real friction).
- Token refresh for GitHub/Jira connector credentials — not blocking
  Phase 2, but should land before this is used somewhere long-lived.
- Ingestion/indexing status visibility in the frontend — candidate for a
  small addition alongside Phase 2's UI work, not a blocker.

## Addendum: raw/LLM split + multi-provider BYOK

Landed after this retro was written, still within Phase 1 scope (no new
phase). The Context Searcher originally always called OpenAI for
synthesis (ADR 0007). It now defaults to a raw retrieval mode — sources
with excerpts and direct links, zero LLM involvement, always free — with
LLM synthesis as an explicit opt-in across four providers (OpenAI, Groq,
Anthropic, Gemini), BYOK or a small rate-limited OpenAI free tier. Also:
the GitHub connector now ingests commit messages alongside PRs, not PRs
only. Full rationale in ADR 0008; this file's "what shipped"/"what was
harder than expected" sections above are left as the accurate record of
this phase's original ship date, not rewritten.
