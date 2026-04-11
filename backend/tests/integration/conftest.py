"""Integration-test shared helpers — Postgres reachability probing.

The integration tier requires a live PostgreSQL. Tests that depend on it must
guard themselves via the :data:`POSTGRES_REACHABLE` module-level constant or
the :func:`skip_unless_postgres` marker factory. When no database is
available the tests are skipped (not failed) so that the unit-test tier can
run in isolation on developer workstations.
"""

from __future__ import annotations

import os
import socket
from collections.abc import AsyncIterator
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


def _postgres_reachable() -> bool:
    """Return ``True`` iff a TCP connection to the configured DB succeeds.

    Uses a short timeout so the check does not inflate the no-postgres code
    path.

    Returns:
        bool: ``True`` when a Postgres port is reachable, ``False`` otherwise.
    """
    url = os.environ.get("BC_DATABASE_URL", "")
    if not url:
        return False
    # Reason: ``postgresql+asyncpg://user:pw@host:port/db`` — urlparse is happy
    # with ``postgresql+asyncpg`` so we map it to plain ``postgresql`` first.
    parsed = urlparse(url.replace("postgresql+asyncpg", "postgresql"))
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


POSTGRES_REACHABLE = _postgres_reachable()


skip_unless_postgres = pytest.mark.skipif(
    not POSTGRES_REACHABLE,
    reason="No Postgres reachable at BC_DATABASE_URL",
)


@pytest_asyncio.fixture(scope="session")
async def engine_session() -> AsyncIterator[None]:
    """Session-scoped engine setup.

    Configures the module-level engine once per test session and disposes it
    at teardown. Tests depending on this fixture should be decorated with
    :data:`skip_unless_postgres`.
    """
    from app.infra.db.session import configure_engine, dispose_engine

    configure_engine()
    yield None
    await dispose_engine()


@pytest_asyncio.fixture
async def db_session(engine_session: None) -> AsyncIterator[AsyncSession]:
    """Function-scoped :class:`AsyncSession` rolled back after each test.

    Yields:
        AsyncSession: Active session. Any data inserted is rolled back.
    """
    del engine_session
    from app.infra.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
