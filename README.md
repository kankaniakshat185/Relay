# Relay

A shared context engine that correlates data across GitHub, Slack, and Jira — exposed through six purpose-built query interfaces built on **one** retrieval/correlation engine, not six disconnected integrations. Ask a question, pick a file, a pull request, or a time window; Relay traces the connections across every source you've connected and answers from there.

**Live demo:** `https://therelay.vercel.app` — sign in with GitHub/Slack/Google to try it.

## The core bet

Most "integrate GitHub + Slack + Jira" projects are three separate connectors, each wired straight into its own feature. Relay's architecture makes a specific, falsifiable bet instead: retrieval, correlation, ranking, and LLM synthesis are genuinely reusable across query types, so they live in one `engine/` layer that every feature calls into, never duplicates.

That bet has been tested twice by real feature work, not just asserted:
- `engine/correlation` was extracted mid-project when **Who Should I Ask** needed the exact ticket-correlation logic **Archaeology** already had.
- `engine/synthesis` was extracted when **Weekly Digest** needed **Context Search**'s LLM-synthesis logic.
- Most recently, **PR Blast Radius** (rank everyone who touched a pull request) shipped as a new `target_type` on an existing endpoint, not a seventh page — see [ADR 0023](docs/adr/0023-pr-blast-radius-entry-point.md) — specifically because the ranking pipeline needed zero changes, only how the file set gets resolved.

A `features/*` module is not allowed to import another `features/*` module, only `engine/`. When two features independently need the same logic, that's a signal it belongs in the engine — not a reason to cross-import.

## Features

Six query modes, one engine underneath every one of them:

| Mode | What it does |
|---|---|
| **Context Search** | Ask a question in plain English; get an answer synthesized from connected GitHub/Slack/Jira activity with real source citations. Raw retrieval is free and on by default; AI-summary mode supports OpenAI, Anthropic, Groq, or Gemini (BYOK, or a rate-limited free tier). |
| **Codebase Archaeology** | Pick a file; Relay traces its live git blame (GitHub GraphQL) back through each commit to the PR that introduced it, the Jira ticket it closed, and the Slack discussion happening at the time. |
| **Who Should I Ask** | Ranks everyone who's touched a file, a directory, or a specific pull request ("PR Blast Radius") by recency or frequency of contribution — including reviewers who commented without ever committing. |
| **Flaky Test Investigator** | Tracks each GitHub Actions workflow's pass/fail history and flags what looks flaky rather than genuinely broken, using real per-attempt outcome data with a documented heuristic fallback where ground truth isn't available. |
| **Notes** | Freeform notes, or ones annotated onto a specific commit/PR/ticket/Slack message. Indexed the same way every connector's data is, so notes surface in Context Search too — a fourth searchable source, not a bolt-on. |
| **Weekly Digest** | A time window instead of a keyword: everything across GitHub, Slack, Jira, and Notes in the last N days, optionally synthesized into what shipped, what's still being discussed, and what looks unresolved. |

## Architecture

```mermaid
flowchart TB
    Browser["Browser"]
    Frontend["Next.js frontend (Vercel)<br/>/api/* → BFF proxy (ADR 0024)"]

    subgraph API["FastAPI backend (Render)"]
        direction TB
        Auth["auth/<br/>login OAuth — GitHub · Slack · Google"]
        Connectors["connectors/<br/>data-access OAuth + API clients<br/>GitHub · Slack · Jira"]

        subgraph Features["features/ — one router + service per query mode"]
            direction LR
            CS["context_search"]
            Arch["archaeology"]
            WTA["who_to_ask<br/>+ PR Blast Radius"]
            FT["flaky_tests"]
            Notes["notes"]
            WD["weekly_digest"]
        end

        subgraph Engine["engine/ — shared retrieval & correlation core"]
            direction LR
            Ingestion["ingestion"]
            Indexing["indexing<br/>hybrid keyword + vector search"]
            Correlation["correlation"]
            Ranking["ranking<br/>differential-tested"]
            CodeContext["code_context<br/>live git blame"]
            CodeSearch["code_search"]
            Synthesis["synthesis<br/>BYOK / free-tier LLM"]
        end
    end

    Worker["Celery worker<br/>15-min periodic resync + indexing"]

    DB[("Neon Postgres<br/>+ pgvector")]
    Cache[("Redis<br/>broker")]

    Providers["GitHub · Slack · Jira APIs"]
    LLMs["OpenAI · Anthropic · Groq · Gemini"]

    Browser -->|same-site cookie| Frontend
    Frontend -->|proxied, server-side| Auth
    Frontend -->|proxied, server-side| Features
    Features --> Engine
    Connectors --> Providers
    Auth --> DB
    Engine --> DB
    Worker --> Connectors
    Worker --> Engine
    Worker --> Cache
    Engine --> LLMs
```

`connectors/*` is the only place that talks to GitHub/Slack/Jira's real APIs — everything else works against `ingested_items`, one normalized table every connector writes into the same shape. Retrieval is genuinely polymorphic across the four query shapes above it: a keyword (Context Search), a file/directory/PR (Who Should I Ask), git history (Archaeology), and a time window (Weekly Digest) all resolve to "relevant items" through the same engine, not four parallel implementations.

## Engineering deep dives

A few pieces of this system involved a real decision under uncertainty, not just wiring libraries together.

### Empirically calibrated correlation threshold

**Problem:** deciding whether a Slack message or Jira ticket is genuinely *related* to a piece of code, not just superficially similar, needs a cutoff on the hybrid search score. An arbitrary threshold either buries real correlations or surfaces noise as if it were signal.

**Approach:** rather than guessing a round number, [`engine/correlation/service.py`](apps/api/src/relay_api/engine/correlation/service.py) measured the actual score distributions of genuine matches vs. noise on real ingested data — genuine matches scored 0.58–0.66; non-matches topped out at 0.384.

**Result:** `_MIN_RELEVANCE_SCORE = 0.48`, placed near the midpoint of that gap rather than hugging the noise ceiling — biased toward precision over recall for a feature that presents results as "this is related," a stronger claim than raw search ever makes.

**Tradeoff:** the threshold is derived from one observed dataset, not a formal precision/recall curve — it's a documented, reasoned calibration, not a guarantee that holds at every possible scale.

### Differential-tested ranking, not one "correct" answer

[`engine/ranking`](apps/api/src/relay_api/engine/ranking/strategies.py) implements two scoring strategies over the same touch history — recency-weighted (exponential half-life decay) and frequency-weighted (raw touch count). They're expected to *disagree*, not converge:

> Carol fixed one bug yesterday. Dave wrote most of the file in a burst eight months ago and hasn't touched it since. Recency favors Carol; frequency favors Dave. Neither answer is wrong.

Instead of picking a winner, [`tests/differential/test_ranking_strategies.py`](apps/api/tests/differential/test_ranking_strategies.py) asserts where the two strategies agree, and documents — with this exact fixture — where and why they diverge. `features/who_to_ask` exposes both as a user-facing choice rather than collapsing them into one hybrid score, unlike `engine/indexing`'s search ranking, which does use a fixed 0.4/0.6 keyword/vector blend because there both signals are meant to agree.

### A cross-site cookie bug, found and fixed before it reached users — then found again in a harder form

Moving from `localhost` to real Vercel/Render domains changes cookies from same-site to cross-site. `SameSite=None; Secure` is necessary but not sufficient: Safari's Intelligent Tracking Prevention blocks cross-site cookies on `fetch`/XHR regardless of that attribute — no cookie flag fixes it while the frontend and backend are genuinely different sites.

The real fix ([ADR 0024](docs/adr/0024-bff-proxy-for-safari-cookie.md)): a BFF proxy. `next.config.ts`'s `rewrites()` proxies every `/api/v1/*` call server-side to the backend, so from the browser's perspective — including the OAuth callback that mints the session cookie — every request stays on one site. This replaced the `SameSite=None` workaround rather than sitting alongside it, since removing the cross-site request is the only thing that actually works in Safari.

### A production incident traced to a library default, not a typo

Live symptom: connecting a GitHub/Slack account intermittently returned a raw Internal Server Error, but refreshing the page showed the connection had actually succeeded. Both this *and* every background sync job started failing outright after switching from local Redis to Upstash (managed, TLS-only Redis).

Tracing it down (in order, each confirmed against source or live logs before moving on, not guessed):
1. Upstash issues `rediss://` URLs. Celery's Redis transport refuses to connect over `rediss://` at all without an explicit `ssl_cert_reqs` — every `.delay()` call raised, uncaught, *after* the connector credential had already been committed to the database, which is exactly why a refresh showed it connected anyway.
2. Fixing that unmasked a second, unrelated bug: the Celery worker process never imports `auth/models.py` (only the web process's router chain does), so `ConnectorCredential`'s string-based `ForeignKey("users.id")` couldn't resolve — `NoReferencedTableError`, on the very first real `db.commit()` in production.
3. Fixing *that* unmasked a third problem: Upstash's free-tier 500,000-request monthly cap, fully exhausted in about a week. Reading kombu's own transport source (`Transport.brpop_timeout = 1`) showed why: an idle Celery worker polls Redis with a blocking `BRPOP` roughly once a second, forever, independent of whether any task ever runs — about 86,400 requests/day from a worker doing nothing.

Fix: `broker_transport_options={"polling_interval": 30}` plus `--without-gossip --without-mingle --without-heartbeat` on a single-worker deployment. Idle polling drops to ~2,880 requests/day; real task latency is unaffected at this scale (jobs already take longer than 30s to run). Each of the three bugs above is now defended by a regression test rather than fixed by inspection alone.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy 2.0 (async), Alembic |
| Database | PostgreSQL + pgvector (hybrid keyword/vector search), hosted on Neon |
| Background jobs | Celery + Redis |
| LLM synthesis | OpenAI, Anthropic, Groq, Gemini — BYOK or rate-limited free tier |
| Auth | OAuth 2.0 (GitHub, Slack, Google for login; GitHub, Slack, Jira for data access — deliberately separate apps, [ADR 0003](docs/adr/0003-two-token-auth-model.md)) |
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS |
| Observability | Sentry, structured JSON logging |
| CI | GitHub Actions — ruff, mypy (strict), pytest with a coverage gate |
| Hosting | Render (backend + Celery worker), Vercel (frontend), Neon (Postgres) |

## Testing and correctness

```
314 tests passing · 94.6% coverage on engine/ + features/ · CI gate at 85%
```
(Coverage and test count reflect a real, fresh run of the suite, not a stale figure.)

Three kinds of test, each checking a different thing:
- **Unit** — mocks connectors/correlation at the boundary; tests each module's own logic (ranking math, ticket-key extraction, LLM provider error normalization).
- **Integration** — a real Dockerized `pgvector/pgvector:pg16` Postgres, exercising real SQL (`to_tsvector`, `cosine_distance`, `ON CONFLICT` upserts) that doesn't run against SQLite.
- **Differential** — `engine/ranking`'s two strategies, tested against synthetic touch histories built specifically to make them disagree (see above), so a real behavioral difference is asserted, not just "it returns something."

CI (`.github/workflows/ci.yml`) runs ruff, `ruff format --check`, `mypy --strict`, and the full suite against a real Postgres+Redis service, failing the build under 85% coverage on `engine/` + `features/`.

## Build and run locally

**Prerequisites:** Node 22.13+, pnpm, Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker (for local Postgres/Redis).

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

# Celery beat (separate terminal) — re-runs indexing for every connected
# provider every 15 minutes, so activity that happens after the initial
# connect eventually becomes searchable too, not just what existed at
# connect time.
uv run --package relay-api celery -A relay_api.jobs.celery_app beat --loglevel=info

# Frontend (separate terminal)
pnpm install
cp apps/web/.env.example apps/web/.env.local
pnpm --filter @relay/web dev
```

Backend runs at `http://localhost:8000`, frontend at `http://localhost:3000`. Sign in, then visit `/connections` to connect GitHub/Slack/Jira and `/search` to query them once the Celery worker has finished indexing.

```bash
# Backend tests need DATABASE_URL exported to your own container/port if it
# differs from pytest's CI-matching default (postgresql+asyncpg://relay:relay@localhost:5432/relay_test)
uv run --package relay-api pytest apps/api/tests
pnpm --filter @relay/web lint
```

## Project structure

```
apps/api/src/relay_api/
├── main.py               # app wiring only — CORS, router registration
├── auth/                 # login OAuth (GitHub · Slack · Google)
├── connectors/            # data-access OAuth + API clients (GitHub · Slack · Jira)
├── engine/                # shared retrieval/correlation core (see Architecture)
├── features/              # one router + service per query mode
└── jobs/                  # Celery app, periodic resync, indexing tasks
apps/web/                  # Next.js (App Router) frontend
docs/
├── adr/                   # technical architecture decisions — what, why, how
├── decisions/              # product/scope decisions — what got cut and why
└── phases/                 # a retro per shipped phase, including bugs found live
```

## Deployment

Backend (FastAPI + Celery worker, combined into one process — Render's free tier has no standalone background-worker service, so the worker+beat process runs backgrounded inside the same web service) on **Render**, frontend on **Vercel**, database on **Neon** (serverless Postgres with pgvector). `render.yaml` (repo root) is a live Render Blueprint documenting the exact build/start commands and environment variables.

Login and data-access OAuth are deliberately separate app registrations per provider ([ADR 0003](docs/adr/0003-two-token-auth-model.md)) — six OAuth apps total across GitHub, Slack, Google, and Jira. All six register their callback URL under the **frontend's** domain, not the backend's — see the BFF proxy deep-dive above.

## Limitations and explicitly deferred work

- **One connected account per provider.** A deliberate Phase 1 simplification, not an oversight — documented in `connectors/models.py`.
- **Ticket-key extraction is a documented heuristic** (a regex over common Jira key shapes), not NLP — see [ADR 0010](docs/adr/0010-live-blame-and-repo-browsing.md). It works well for teams that reference ticket keys in commits/PRs; it has no fallback for teams that don't.
- **No frontend automated test suite** — CI runs ESLint and `tsc`/`next build` type-checking, not a test runner. Backend correctness is where the test investment went.
- **A Drift/Stale-Ticket Finder and a Dependency Alert Bot were both scoped and explicitly not built** — the reasoning for each cut is written up in [`docs/decisions/`](docs/decisions/), not just dropped silently.
- **PR Blast Radius is reachable only through a search hit today** — no way to jump to an arbitrary PR by number if it hasn't already been indexed (same scope line the ticket/PR-first search entry point already carries, see [ADR 0023](docs/adr/0023-pr-blast-radius-entry-point.md)).

## Documentation

- [`docs/adr/`](docs/adr/) — technical architecture decisions: what, why, how. Written when a real design decision is made, not retroactively.
- [`docs/decisions/`](docs/decisions/) — product/scope decisions: what got cut or deliberately deferred, and the actual reasoning.
- [`docs/phases/`](docs/phases/) — a retro per shipped phase, including a "found live, not just in review" section for bugs that only surfaced against real data.
- [`plan.md`](plan.md) — the original architecture/phase plan this project was built against.

## License

MIT
