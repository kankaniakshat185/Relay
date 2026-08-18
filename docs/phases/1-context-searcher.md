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
- ~~Token refresh for GitHub/Jira connector credentials~~ — done for Jira
  (the only one that actually issues short-lived tokens today), see the
  addendum below. GitHub's classic OAuth app tokens don't expire, so
  there's nothing to refresh there yet; revisit only if GitHub ever moves
  to a GitHub App with expiring tokens.
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

## Addendum: what a real end-to-end run surfaced

Connecting all three providers to real accounts and actually running
search — not just unit/integration tests against mocks — surfaced several
bugs no amount of mocked testing would have caught, since each one is
specifically about behavior at the boundary with a live service or a
long-running worker process:

- **Celery never ran a single indexing task.** `autodiscover_tasks`'
  default `related_name="tasks"` silently found nothing, since the task
  lives in `jobs/indexing.py` — zero error, just an empty task registry.
  Every connector-connect indexing job had been vanishing into the Redis
  queue with nothing to consume it since Phase 1 shipped. Fixed with an
  explicit `related_name`, caught for good with a registration test
  (`test_celery_app.py`) — this class of bug is exactly what "add a test"
  means when the failure mode is silence, not an exception.
- **A worse version of the pytest event-loop bug, in production code.**
  `core/db.py`'s engine is a correct singleton for FastAPI (one persistent
  loop for the process's life) but wrong for Celery's prefork workers,
  which reuse the same child process across many tasks while
  `index_connector_task` calls `asyncio.run(...)` — a new loop every task.
  GitHub and Slack indexing (each worker process's first task) worked;
  Jira's retry, routed to an already-used process, failed with zero rows
  ever reaching the DB. Fixed with `engine.dispose()` at the top of every
  task (SQLAlchemy's own documented fix for this exact scenario).
- **Atlassian retired the Jira search endpoint we built against.**
  `GET /rest/api/3/search` now returns `410 Gone`; the replacement,
  `POST /rest/api/3/search/jql`, also rejects an unbounded `ORDER BY`
  with no restriction clause. Fixed by migrating to the new endpoint with
  a genuine `updated >= -365d` bound — which also better matches "recent
  activity" the way GitHub/Slack already scope themselves.
- **Jira's access token expiry is the "no refresh flow" gap, hit for
  real.** Flagged as an open item in this retro's first draft; a ~1 hour
  token expiry during a testing session made it concrete. Reconnecting
  was the workaround at the time — since resolved, see the addendum below.
- **Gemini's batch embedding endpoint caps at 100 items per call**; a
  single GitHub indexing pass (10 repos × up to 40 PRs+commits each) can
  produce ~400. OpenAI's much higher limit is why this never surfaced
  before adding Gemini as a provider option (ADR 0009). Fixed generically
  — `embed_texts` chunks into batches of 96 regardless of which provider
  is active, not a Gemini-specific patch.
- **A real commit with no line breaks blew past `title`'s column limit.**
  `message.splitlines()[0]` returns the *entire* message when there's no
  newline — hit on an actual commit from a real repo, not a crafted edge
  case. Fixed with a shared `truncate_title` helper applied to every
  connector's title field, not just GitHub's commits.
- **One Slack channel the bot wasn't invited to failed the entire indexing
  run**, losing every channel that *would* have worked. `conversations.list`
  returns channels the bot can see, not channels it's a member of — only
  `conversations.history` enforces membership. Fixed by catching a
  per-channel failure and continuing, logging a warning instead of
  aborting the whole provider's ingestion.
- **Embeddings had zero error handling anywhere**, even though every
  search depends on them unconditionally (raw mode included) — an OpenAI
  quota error was a raw 500 with a stack trace. Fixed with
  `EmbeddingUnavailableError` + an app-level exception handler mapping it
  to a clean `503`.

None of these were architecture mistakes — the design held up. They were
all "the real world doesn't match the mock" gaps, found because the
system got run for real before being called done.

## Addendum: Jira token refresh

Closes the "no token refresh flow" gap called out above and in "open
items carried forward" — manual reconnection was the only recovery from
Jira's ~1 hour access token expiry.

- `connectors/base.py` gained a second, optional `RefreshableConnectorProvider`
  protocol (plus a `RefreshedTokens` result type) — deliberately separate
  from `ConnectorProvider` rather than adding a required method to it,
  since GitHub's classic OAuth tokens and Slack's bot tokens don't expire
  and have nothing to implement here.
- `connectors/registry.get_refreshable_provider(name)` is the single place
  that knows only Jira implements it today — `None` for everything else,
  treated as "nothing to refresh" rather than an error.
- `connectors/service.ensure_valid_access_token(db, credential)` is the
  new entry point: passes non-expiring or not-yet-expiring tokens straight
  through, and for anything else expired with a refresh path available,
  calls the provider's refresh grant, persists the (Atlassian rotates
  these) new access + refresh tokens and expiry, and returns the fresh
  token — all before `jobs/indexing.py` makes a single API call.
- A refresh grant itself failing (revoked/expired refresh token — the one
  case reconnecting is still genuinely required for) raises
  `TokenRefreshError`; `_run_indexing_for_connector` catches it, logs a
  warning, and skips that run instead of the job crashing outright.
