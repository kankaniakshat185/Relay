"""Async SQLAlchemy engine + session management.

Every model in the app inherits from `Base`. `get_db` is the FastAPI
dependency that hands routes a request-scoped `AsyncSession`.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from relay_api.core.config import get_settings


class Base(DeclarativeBase):
    """Shared declarative base. Alembic's `env.py` imports this for autogenerate."""


settings = get_settings()

engine = create_async_engine(settings.database_url, pool_pre_ping=True)

async_session_factory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
