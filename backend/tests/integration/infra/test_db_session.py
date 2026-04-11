"""Integration tests for :mod:`app.infra.db.session` (requires Postgres)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import skip_unless_postgres

pytestmark = [pytest.mark.integration, skip_unless_postgres]


async def test_get_session_yields_working_session(db_session: AsyncSession) -> None:
    """A basic SELECT 1 round-trip succeeds."""
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1


async def test_rollback_on_error(db_session: AsyncSession) -> None:
    """Errors inside a session are rolled back cleanly."""
    try:
        await db_session.execute(text("SELECT * FROM __missing_table__"))
    except Exception:
        await db_session.rollback()
    # Session still usable after rollback
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1


async def test_session_isolated_per_test(db_session: AsyncSession) -> None:
    """Each test starts with a fresh session that can execute queries."""
    result = await db_session.execute(text("SELECT current_database()"))
    assert result.scalar_one() is not None
