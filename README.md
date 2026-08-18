# Relay

A shared context engine that correlates data across GitHub, Slack, and
Jira, exposed through multiple purpose-built query interfaces (context
search, codebase archaeology, "who should I ask") plus two standalone
subsystems (flaky test investigation, dependency breaking-change alerts).

The core architectural bet: **one retrieval/correlation engine, several
query modes** — not four disconnected integrations. See
[`plan.md`](plan.md) for the full architecture, phase plan, and scope, and
[`docs/adr/`](docs/adr/) / [`docs/decisions/`](docs/decisions/) for why
things are the way they are.

## Status

Phase 1 (Context Searcher vertical slice) — see [`plan.md` §5](plan.md#5-phases)
for the phase plan. Login OAuth (GitHub/Slack/Google), connector OAuth
(GitHub/Slack/Jira, read-only — GitHub covers PRs and commit messages),
and the correlation engine (ingestion + hybrid keyword/vector indexing,
ADR 0006, embedding provider swappable to a free Gemini tier, ADR 0009)
are wired end-to-end. The Context Searcher has two modes:
raw retrieval (default, no LLM, always free) and an optional AI-summary
mode across OpenAI/Groq/Anthropic/Gemini — BYOK, or a rate-limited OpenAI
free tier (ADR 0007, ADR 0008). Archaeology and Who-Should-I-Ask (querying
the same engine) land in Phase 2.

## Repo layout

```
apps/web/     Next.js frontend
apps/api/     FastAPI backend
packages/     Shared packages (generated types, etc.)
docs/adr/     Technical architecture decisions
docs/decisions/  Product/scope decisions — what got cut, and why
docs/phases/  Per-phase retros, written after each phase ships
```

## Local development

**Prerequisites:** Node 22.13+, pnpm, Python 3.12+, [uv](https://docs.astral.sh/uv/),
Docker (for local Postgres/Redis).

```bash
# Backend
uv sync
cp apps/api/.env.example apps/api/.env
# Fill in: SECRET_KEY, CONNECTOR_ENCRYPTION_KEY, OPENAI_API_KEY, and the
# GitHub/Slack/Google login + GitHub/Slack/Jira connector OAuth app
# credentials — see .env.example for how to generate the two secret keys.
# No OpenAI billing yet? Set EMBEDDING_PROVIDER=gemini and GEMINI_API_KEY
# instead — a free AI Studio key works, no credit card needed (ADR 0009).

# NOT plain postgres:16-alpine — needs the pgvector extension (ADR 0006).
docker run -d --name relay-pg -e POSTGRES_USER=relay -e POSTGRES_PASSWORD=relay \
  -e POSTGRES_DB=relay -p 5432:5432 pgvector/pgvector:pg16
docker run -d --name relay-redis -p 6379:6379 redis:7-alpine

uv run --package relay-api alembic -c apps/api/alembic.ini upgrade head
uv run --package relay-api uvicorn relay_api.main:app --app-dir apps/api/src --reload

# Celery worker (separate terminal) — runs the indexing job triggered when
# a connector finishes connecting; the API is functional without it, but
# nothing gets ingested/indexed until it's running.
uv run --package relay-api celery -A relay_api.jobs.celery_app worker --loglevel=info

# Frontend (separate terminal)
pnpm install
cp apps/web/.env.example apps/web/.env.local
pnpm --filter @relay/web dev
```

Backend runs at `http://localhost:8000`, frontend at `http://localhost:3000`.
Sign in, then visit `/connections` to connect GitHub/Slack/Jira and
`/search` to query them once the Celery worker has finished indexing.

## Tests

```bash
uv run --package relay-api pytest apps/api/tests   # backend (needs the pgvector Postgres running + migrated)
pnpm --filter @relay/web lint                       # frontend lint
```

## License

MIT
