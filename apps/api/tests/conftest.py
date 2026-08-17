"""Shared pytest fixtures.

Phase 0 keeps this deliberately small — a real Postgres-backed integration
fixture (matching the CI Dockerized-Postgres service) lands alongside the
first integration test suite in Phase 1.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from relay_api.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
