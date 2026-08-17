"""Proves the app boots and the CI pipeline (Docker Postgres/Redis services,
pytest, coverage) actually runs end to end. Real integration coverage for
`features/*` starts in Phase 1.
"""

from httpx import AsyncClient


async def test_healthz(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
