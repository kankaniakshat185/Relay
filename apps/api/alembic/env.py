import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Make `relay_api` importable when Alembic is invoked from apps/api/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Import every model module so it registers on Base.metadata before
# autogenerate runs. Add new model modules here as they're created.
from relay_api.auth import models as auth_models  # noqa: E402, F401
from relay_api.connectors import models as connector_models  # noqa: E402, F401
from relay_api.core.config import get_settings  # noqa: E402
from relay_api.core.db import Base  # noqa: E402
from relay_api.engine.ingestion import models as ingestion_models  # noqa: E402, F401

# Note: autogenerate does NOT add the `import pgvector.sqlalchemy` a new
# Vector column needs — it renders `pgvector.sqlalchemy.vector.VECTOR(...)`
# but the import has to be added to the generated file by hand each time.
# pgvector has no first-party alembic integration; this is a known gap.

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Use the app's own settings (env vars / .env) rather than duplicating the
# connection string in alembic.ini.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
