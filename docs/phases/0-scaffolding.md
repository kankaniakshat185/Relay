# Phase 0 retro: Scaffolding

**Shipped:** 2026-08-17

## What shipped

- Monorepo structure matching plan.md §2: `apps/web`, `apps/api`,
  `packages/shared-types`, `docs/{adr,decisions,phases}`.
- Backend: FastAPI app factory (`main.py`), structured JSON logging, Sentry
  wiring (no-op without a DSN), async SQLAlchemy 2.0 + Alembic with a
  baseline migration for `users` + `auth_identities`, `/v1` prefix,
  `/healthz`.
- Login OAuth, fully working end-to-end for GitHub, Slack, and Google:
  authorization-URL building, CSRF `state` verification, code exchange,
  find-or-create user, session cookie. No connector OAuth yet — that's
  Phase 1 (see ADR 0003).
- Frontend: Next.js App Router with `(auth)/login` and a protected
  `(dashboard)` shell, both wired against the real backend (not mocked).
  TypeScript strict mode, Tailwind, ESLint clean.
- CI: GitHub Actions with a backend job (ruff, ruff format, mypy --strict,
  Dockerized Postgres + Redis services, pytest with coverage gate) and a
  frontend job (eslint, `next build` for type-checking). Verified the exact
  CI commands locally against a throwaway Postgres container before
  committing the workflow, rather than trusting it untested.
- 5 ADRs, 2 scope-decision docs (see `docs/adr/`, `docs/decisions/`).

## What got cut within this phase

- Connector OAuth (`connectors/github|slack|jira`) and the Connections
  page — these are Phase 1 scope per plan.md §5, not Phase 0. The
  directories exist as empty stubs with scoping docstrings, nothing more.
- The engine (`engine/ingestion|indexing|ranking`) and all `features/*`
  packages — same reasoning, empty stubs only. Coverage gate doesn't
  meaningfully apply yet because there's no code to cover (confirmed
  locally: 0 statements reports as 100% covered, so the 85% gate doesn't
  block Phase 0 for the right reason — not because it's broken).
- Phase-N frontend routes (`search/`, `archaeology/`, etc.) were not
  pre-created. The dashboard nav references them but leaves them
  unlinked/disabled with a "ships in Phase N" label, rather than scaffolding
  empty route folders ahead of the phase that owns them.

## What was harder than expected

The session-cookie-domain problem (ADR 0004) wasn't anticipated when the
stack was chosen — it surfaced while actually wiring the dashboard guard.
Because the login session cookie is minted during the backend's own OAuth
callback route, it's scoped to the backend's domain, not the frontend's.
That's invisible in local dev (same-ish origin behavior is easy to get
lucky with) but would have quietly broken any server-component auth check
in production, where frontend and backend are genuinely different domains.
Resolved by making the Phase 0 dashboard guard client-side on purpose
(`AuthGuard.tsx`) rather than reaching for a server-side cookie read that
would have worked locally and failed on Vercel/Render. Written up in ADR
0004 so the reasoning doesn't get relitigated by accident later.

## Open items carried forward (unchanged from plan.md §9)

- Embedding model / vector search approach for `engine/indexing` — must be
  decided before Phase 1 build starts in earnest.
- Dockerized Postgres in CI vs. Neon branch-per-PR — revisit only if the
  Docker approach starts causing real friction.
