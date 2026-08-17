"""Fixtures for tests that need a real (migrated) Postgres — see plan.md §6:
these exercise raw SQL (`to_tsvector`, `cosine_distance`, `ON CONFLICT`)
that doesn't run against SQLite, so they're integration tests, not unit
tests, and run against the CI Dockerized `pgvector/pgvector:pg16` service.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.core.db import async_session_factory


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def test_user(db: AsyncSession) -> User:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.com", display_name="Test User")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
