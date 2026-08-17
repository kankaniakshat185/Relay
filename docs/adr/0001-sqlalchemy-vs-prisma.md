# ADR 0001: SQLAlchemy 2.0 (async) over the Prisma Python client

**Status:** Accepted — Phase 0

## What

The backend ORM is SQLAlchemy 2.0 in async mode, with Alembic for migrations,
rather than the Prisma Python client.

## Why

This was a genuine toss-up going in, not a rubber stamp. Prisma's schema
language and migration UX are nicer than anything in the Python ecosystem —
if the backend were TypeScript, Prisma would win without much debate.

But the backend is FastAPI, and on the Python side the two options aren't
peers in maturity:

- **Prisma Python client** is community-maintained (`prisma-client-py`), not
  an official Prisma product. Its async support and migration tooling lag
  behind the JS/TS client by a meaningful margin, and the amount of
  Stack-Overflow-and-GitHub-issue coverage for "this broke at 2am" is thin.
- **SQLAlchemy 2.0 async + Alembic** is the de facto standard for
  FastAPI backends. It's what most production FastAPI codebases actually
  run, which means better docs, better editor/type support, and a much
  higher chance that a weird error message has already been answered
  somewhere.

Given the backend is Python end to end, betting on the ecosystem's default
tool beat betting on a nicer-but-thinner client library.

## How

- `apps/api/src/relay_api/core/db.py` defines the shared async engine,
  session factory, and declarative `Base`.
- Every model inherits from `Base`; Alembic's `env.py`
  (`apps/api/alembic/env.py`) imports `Base.metadata` plus each model module
  so `alembic revision --autogenerate` picks up new tables automatically.
- Migrations are checked in under `apps/api/alembic/versions/` and applied
  as a pre-deploy step on Render (see plan.md §7).
