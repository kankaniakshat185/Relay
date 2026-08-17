# ADR 0002: Monorepo, pnpm workspaces without Turborepo, uv workspace for Python

**Status:** Accepted — Phase 0

## What

Relay is one repository containing both `apps/web` (Next.js) and `apps/api`
(FastAPI), plus shared packages. The frontend side uses plain pnpm
workspaces (no Turborepo yet). The Python side uses a `uv` workspace with a
single root lockfile.

## Why

**Monorepo vs. polyrepo:** the whole architectural bet of this project is
"one correlation engine, several query interfaces" (see ADR 0005). A
frontend and backend that ship together every phase (plan.md §5) and share
generated types (`packages/shared-types`) benefit from being versioned and
reviewed together — a polyrepo would mean coordinating PRs across two repos
for every phase, for no real isolation benefit at this size.

**pnpm workspaces without Turborepo:** Turborepo earns its keep on build
caching and task orchestration across many packages. Relay has exactly two
JS packages right now (`apps/web`, `packages/shared-types`) — there's no
build graph complex enough to need caching yet. Adding Turborepo now would
be tooling for a problem that doesn't exist. Revisit if/when build times
actually start hurting.

**uv workspace, single lockfile:** `apps/api` is the only Python package
today, but the workspace is set up from the start (`[tool.uv.workspace]` in
the root `pyproject.toml`) so a second Python package — e.g. a shared
`relay-schemas` package, if `packages/shared-types` ever needs a Python-side
counterpart — doesn't require restructuring later. `uv` was chosen over
Poetry for faster installs and native workspace support without a plugin.

## How

```
relay/
├── apps/
│   ├── web/            pnpm workspace member (apps/web/package.json)
│   └── api/             uv workspace member (apps/api/pyproject.toml)
├── packages/
│   └── shared-types/    pnpm workspace member, empty until Phase 1
├── pnpm-workspace.yaml   lists apps/web, packages/*
└── pyproject.toml        [tool.uv.workspace] members = ["apps/api"]
                           also holds shared ruff/mypy config for the whole
                           Python side
```

`uv sync` at the repo root installs and links the whole Python workspace.
`pnpm install` at the repo root installs and links the whole JS workspace.
