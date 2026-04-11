"""Alembic environment configuration for async PostgreSQL migrations."""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

# Alembic Config object — provides access to values within the .ini file.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from environment variable if set.
# BC_DATABASE_URL takes precedence over the placeholder in alembic.ini.
db_url = os.environ.get("BC_DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# Import target metadata for autogenerate support.
# Reason: Base is not yet implemented at scaffold time (Batch 0 will add it).
# The try/except prevents alembic check from crashing during scaffolding.
try:
    from app.infra.db.base import Base  # noqa: E402

    target_metadata = Base.metadata
except ImportError:
    # Batch 0 will implement app.infra.db.base; until then, autogenerate is disabled.
    target_metadata = None  # type: ignore[assignment]


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine;
    calls to context.execute() emit the given string to the script output.
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


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    """Execute migrations against a live connection."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations against a live async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using asyncio."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
