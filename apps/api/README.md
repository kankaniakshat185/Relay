# relay-api

FastAPI backend for Relay — see the repo root [`plan.md`](../../plan.md) for
the full architecture and phase plan.

## Local dev

```bash
# from repo root
uv sync
cp apps/api/.env.example apps/api/.env   # fill in secrets
uv run --package relay-api alembic -c apps/api/alembic.ini upgrade head
uv run --package relay-api uvicorn relay_api.main:app --app-dir apps/api/src --reload
```

## Tests

```bash
uv run --package relay-api pytest apps/api/tests
```
