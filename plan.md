# Relay — Master Plan

**Status:** Source of truth. This document does not change casually — if a decision here needs to be revisited, it gets its own ADR explaining why, rather than a silent edit here.

**What Relay is:** A shared context engine that correlates data across GitHub, Slack, and Jira, exposed through multiple purpose-built query interfaces (context search, codebase archaeology, "who should I ask") plus two standalone subsystems (flaky test investigation, dependency breaking-change alerts). The core architectural bet is "one retrieval/correlation engine, several query modes" rather than building four disconnected integrations.

---

## 1. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend framework | Next.js (App Router) + React | |
| Styling | Tailwind CSS | |
| Frontend monorepo tooling | pnpm workspaces | No Turborepo for now — add later only if build times actually become a problem |
| Backend framework | FastAPI | async-native |
| ORM | SQLAlchemy 2.0 (async) + Alembic for migrations | Chosen over Prisma Python client — see `docs/adr/0001-sqlalchemy-vs-prisma.md` |
| Python package manager | uv | Workspace support, single lockfile, fast installs |
| Database | Neon Postgres (serverless) | |
| Job queue / scheduling | Redis + Celery | Powers webhook ingestion, polling jobs, background indexing |
| Auth (login) | OAuth via GitHub / Slack / Google — minimal scopes, session-only | Separate from data-access connectors, see §4 |
| Auth (data access) | Per-provider OAuth with broader scopes, connected post-login | |
| Type checking | mypy (strict mode) — backend; TypeScript strict mode — frontend | |
| Lint / format | ruff — backend; eslint + prettier — frontend | |
| CI/CD | GitHub Actions | See §7 |
| Backend + Redis + Celery hosting | Render | |
| Frontend hosting | Vercel | |
| CI test database | Dockerized Postgres service (spun up fresh per CI run) | Default choice — no external branch dependency, no cleanup needed. Open to revisiting (e.g. Neon ephemeral branches) if CI test data needs get more complex later. |
| API versioning | `/v1` prefix on all backend routes from the start | No external consumers yet, but the prefix costs nothing now and avoids a painful migration if a breaking change is ever needed later. |
| Error tracking | Sentry (backend + frontend) | Directly addresses the production-observability gap flagged in past project reviews (BlackRock JD eval) — doubles as a portfolio strength, not just hygiene. |
| Logging | Structured logging (JSON logs, not bare `print`/`console.log`) on the backend | Makes logs searchable/filterable in Render's log viewer and pairs with Sentry for error context. |
| License | MIT | |
| Repo visibility | Public | |

---

## 2. Repo Structure (monorepo)

```
relay/
├── apps/
│   ├── web/                          # Next.js + React + Tailwind
│   │   ├── app/
│   │   │   ├── (auth)/
│   │   │   ├── (dashboard)/
│   │   │   │   ├── search/           # Phase 1
│   │   │   │   ├── archaeology/      # Phase 2
│   │   │   │   ├── who-to-ask/       # Phase 2
│   │   │   │   ├── flaky-tests/      # Phase 3
│   │   │   │   └── dependency-alerts/# Phase 4
│   │   │   └── api/                  # BFF routes only where genuinely needed
│   │   ├── components/
│   │   ├── lib/
│   │   └── package.json
│   └── api/                          # FastAPI backend
│       ├── src/relay_api/
│       │   ├── core/                 # config, db session, security, shared deps
│       │   ├── auth/                 # LOGIN oauth only (GitHub/Slack/Google)
│       │   ├── connectors/           # DATA ACCESS oauth + provider clients
│       │   │   ├── github/
│       │   │   ├── slack/
│       │   │   └── jira/
│       │   ├── engine/               # the shared correlation/retrieval core
│       │   │   ├── ingestion/        # normalizes connector events into a common schema
│       │   │   ├── indexing/         # keyword/embedding index, timestamp correlation
│       │   │   └── ranking/          # scoring strategies — differential-tested
│       │   ├── features/
│       │   │   ├── context_search/       # Phase 1
│       │   │   ├── archaeology/          # Phase 2
│       │   │   ├── who_to_ask/           # Phase 2
│       │   │   ├── flaky_tests/          # Phase 3
│       │   │   └── dependency_alerts/    # Phase 4
│       │   ├── jobs/                 # Celery tasks
│       │   └── main.py               # app factory + router registration ONLY, no business logic
│       ├── tests/
│       │   ├── unit/
│       │   ├── integration/
│       │   └── differential/         # engine/ranking ONLY
│       └── pyproject.toml
├── packages/
│   └── shared-types/                 # OpenAPI-generated TS types consumed by web
├── docs/
│   ├── adr/                          # technical architecture decisions
│   ├── decisions/                    # product/scope decisions (what got cut, and why)
│   └── phases/                       # per-phase plan + retro, written after each phase ships
├── .github/workflows/                # CI/CD
├── pyproject.toml                    # uv workspace root
├── pnpm-workspace.yaml
└── README.md
```

**Module boundary rule (the "no god files" enforcement mechanism):** each `features/*` module owns its own router, service, and schema files, and may only import from `engine/` — never from another `features/*` module. If a feature ever needs another feature's logic, that's a signal the shared logic belongs in `engine/`, not that it's fine to cross-import. Soft ceiling of ~250 lines per file before it should be split; not a hard CI gate, but a review-time flag.

---

## 3. Feature Scope (confirmed, final)

**In scope:**
1. **Context Searcher** — user queries a topic, engine searches GitHub/Slack/Jira and returns a synthesized, source-attributed answer.
2. **Codebase Archaeology Assistant** — traces why a piece of code exists: git blame → originating PR → linked Jira ticket → related Slack discussion at the time.
3. **Who Should I Ask** — given a file/module or question, surfaces likely experts via git blame/PR history + Slack discussion recency.
4. **Flaky Test / CI Failure Investigator** — correlates CI failures against historical flakiness patterns and recent related PRs.
5. **Dependency / Breaking-Change Alert Bot** — watches dependency version bumps, parses changelogs, cross-references against actual usage in the codebase.

**Cut from scope (confirmed):**
- **Email integration** — no feature in the final list actually depends on it; would have added a fourth OAuth/data-access surface for no reasoning-depth gain. Logged in `docs/decisions/`.
- **Tagging / organizing across apps** — lowest usefulness-to-engineering-depth ratio of everything considered; doesn't compose with the shared engine architecture the other features share. Logged in `docs/decisions/`.

**Integrations (final):** GitHub, Slack, Jira. No email.

---

## 4. Auth — Two Distinct Flows

This is a deliberate split, not an accident of scope:

- **Login flow:** user signs in with GitHub / Slack / Google. Minimal scopes (identity + email only). Produces a session. This is *only* about knowing who's using the app.
- **Connector flow:** after login, the user visits a "Connections" page and explicitly grants Relay data-access scopes per provider (repo read, channel history, Jira project access, etc.). Stored separately from the session/login identity, revocable independently, per user, per provider.

Even where the same provider is used for both (e.g. GitHub), these are two separate token records: `auth_identities` (login) and `connector_credentials` (data access). Login working does **not** imply the data connector is connected — the app must handle and clearly surface that distinction in the UI.

---

## 5. Phases

Every phase ships both backend and frontend for its scope — no phase where backend is "done" and frontend is deferred.

| Phase | Backend scope | Frontend scope | What it proves |
|---|---|---|---|
| **0 — Scaffolding** | Monorepo setup, CI pipeline (ruff/mypy/pytest wired but mostly empty), Alembic baseline, login-only auth | Login page, protected dashboard shell | The skeleton deploys end-to-end |
| **1 — Context Searcher (vertical slice)** | `connectors/github`, `connectors/slack`, `connectors/jira` (read-only), `engine/ingestion`, `engine/indexing`, `features/context_search`, Celery indexing job | Connections page (OAuth connect flow per provider), Search page + results UI | The engine + one full query mode, working against real data |
| **2 — Archaeology + Who-to-Ask** | `engine/ranking` (differential-tested here), `features/archaeology`, `features/who_to_ask` — both query the *same* engine built in Phase 1 | Archaeology timeline view, Who-to-ask panel | The "one engine, multiple queries" architecture, concretely demonstrated |
| **3 — Flaky Test Investigator** | CI webhook ingestion, polling job, `features/flaky_tests` (own historical-pattern store — standalone subsystem) | CI status page, flaky-test verdict UI | A standalone subsystem integrates cleanly without polluting the core engine |
| **4 — Dependency Alert Bot** | Changelog parsing, static usage analysis, `features/dependency_alerts` | Alerts dashboard | Second standalone subsystem, same discipline applied twice |

Each phase, on completion, gets:
- An ADR for any technical decision made during that phase (`docs/adr/`)
- A phase retro in `docs/phases/` covering what shipped, what got cut *within* that phase and why, what was harder than expected
- Test coverage meeting the thresholds in §6 before merge to main

---

## 6. Testing Strategy

- **Unit tests** — every service function in `engine/` and every `features/*` module, connectors mocked.
- **Integration tests** — full request → DB round trip per feature endpoint, run against the Dockerized Postgres CI service.
- **Differential tests** — scoped specifically to `engine/ranking/`. Example: two scoring strategies for "who should I ask" (recency-weighted vs. frequency-weighted) run against the same fixture set, asserting where they agree and documenting where they're expected to diverge. Not applied to CRUD or auth routes — there's nothing to differential-test there, and claiming otherwise doesn't hold up under review.
- **Coverage threshold:** 85% minimum on `engine/` and `features/*`, enforced as a CI gate. No hard coverage gate on `apps/web` routing/UI glue — coverage-chasing on JSX return statements is busywork, not signal.

---

## 7. CI/CD (GitHub Actions)

Pipeline runs on every PR and on push to `main`:

1. **Backend job:**
   - `uv sync`
   - `ruff check .` and `ruff format --check .`
   - `mypy --strict`
   - Spin up Dockerized Postgres + Redis services
   - `pytest` (unit + integration + differential) with coverage report
   - Fail build if coverage on `engine/` or `features/*` drops below 85%
2. **Frontend job:**
   - `pnpm install`
   - `eslint .`
   - `tsc --noEmit`
   - Frontend test suite (once established)
3. **On merge to `main`:**
   - Backend + Celery worker deploy to Render
   - Frontend deploy to Vercel
   - Alembic migrations run as a pre-deploy step on Render

Branch protection: PRs require the CI pipeline green before merge. No direct pushes to `main`.

---

## 8. Documentation Conventions

- **`docs/adr/`** — technical architecture decisions only (e.g. SQLAlchemy vs. Prisma, monorepo vs. polyrepo, one-engine-many-queries design). Format: what → why → how, human-written tone, no AI-report boilerplate.
- **`docs/decisions/`** — product/scope decisions: what got cut, what got deferred, why a feature was or wasn't built a certain way. Same what/why/how standard.
- **`docs/phases/`** — per-phase retro, written after each phase ships, not before.

Every ADR and decision doc follows the same shape:
- **What** was decided
- **Why** — the actual reasoning, including alternatives considered and why they lost
- **How** — what it looks like in practice / how it's implemented

---

## 9. Open Items / Explicit Non-Decisions

These are intentionally left open rather than assumed. Flag before starting the relevant phase:

- Embedding model / vector search approach for `engine/indexing` — not yet decided, needs deciding before Phase 1 build starts in earnest.
- Whether Neon branch-per-PR gets adopted later for integration testing (currently: Dockerized Postgres in CI, per your call) — revisit only if the Docker approach starts causing real friction.

**Resolved since first draft:** license (MIT), repo visibility (public), API versioning (`/v1` prefix from the start), observability (Sentry + structured logging) — see §1 for details.

---

*This document is the source of truth for scope, stack, and process. Anything not written here is not yet decided — do not assume defaults on unlisted items; raise them as a question instead.*
