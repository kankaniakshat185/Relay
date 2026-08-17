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

Phase 0 (scaffolding) — see [`plan.md` §5](plan.md#5-phases) for the phase
plan. Login OAuth (GitHub/Slack/Google) is wired end-to-end; the
correlation engine and connectors land in Phase 1.

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

**Prerequisites:** Node 20+, pnpm, Python 3.12+, [uv](https://docs.astral.sh/uv/),
Docker (for local Postgres/Redis).

```bash
# Backend
uv sync
cp apps/api/.env.example apps/api/.env   # fill in SECRET_KEY + OAuth app credentials
docker run -d --name relay-pg -e POSTGRES_USER=relay -e POSTGRES_PASSWORD=relay \
  -e POSTGRES_DB=relay -p 5432:5432 postgres:16-alpine
uv run --package relay-api alembic -c apps/api/alembic.ini upgrade head
uv run --package relay-api uvicorn relay_api.main:app --app-dir apps/api/src --reload

# Frontend (separate terminal)
pnpm install
cp apps/web/.env.example apps/web/.env.local
pnpm --filter @relay/web dev
```

Backend runs at `http://localhost:8000`, frontend at `http://localhost:3000`.

## Tests

```bash
uv run --package relay-api pytest apps/api/tests   # backend
pnpm --filter @relay/web lint                       # frontend lint
```

## License

MIT
