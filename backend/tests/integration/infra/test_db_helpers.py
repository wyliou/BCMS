"""Integration tests for :mod:`app.infra.db.helpers` (requires Postgres)."""

from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.infra.db.helpers import next_version
from tests.integration.conftest import skip_unless_postgres

pytestmark = [pytest.mark.integration, skip_unless_postgres]


class _LocalBase(DeclarativeBase):
    """Throwaway declarative base so the helper test does not touch real tables."""


class _FakeUpload(_LocalBase):
    """Ephemeral model exposing a ``version`` column for :func:`next_version`."""

    __tablename__ = "_test_fake_upload"
    id = Column(Integer, primary_key=True, autoincrement=True)
    cycle_id = Column(Integer, nullable=False)
    version = Column(Integer, nullable=False)


async def _ensure_table(db: AsyncSession) -> None:
    """Create the ephemeral test table inside the current transaction."""
    from sqlalchemy import text as _text

    await db.execute(
        _text(
            "CREATE TEMP TABLE IF NOT EXISTS _test_fake_upload ("
            "id SERIAL PRIMARY KEY, cycle_id INT NOT NULL, version INT NOT NULL)"
        )
    )


async def test_next_version_starts_at_one(db_session: AsyncSession) -> None:
    """An empty filter set returns ``1``."""
    await _ensure_table(db_session)
    result = await next_version(db_session, _FakeUpload, cycle_id=1)
    assert result == 1


async def test_next_version_increments(db_session: AsyncSession) -> None:
    """After inserting v1, the helper returns ``2`` for the same filter."""
    from sqlalchemy import text as _text

    await _ensure_table(db_session)
    await db_session.execute(
        _text("INSERT INTO _test_fake_upload (cycle_id, version) VALUES (:c, 1)"),
        {"c": 42},
    )
    assert await next_version(db_session, _FakeUpload, cycle_id=42) == 2


async def test_next_version_filters_independently(db_session: AsyncSession) -> None:
    """Distinct filters maintain independent version counters."""
    from sqlalchemy import text as _text

    await _ensure_table(db_session)
    await db_session.execute(
        _text("INSERT INTO _test_fake_upload (cycle_id, version) VALUES (:c, :v)"),
        [{"c": 1, "v": 1}, {"c": 1, "v": 2}, {"c": 2, "v": 1}],
    )
    assert await next_version(db_session, _FakeUpload, cycle_id=1) == 3
    assert await next_version(db_session, _FakeUpload, cycle_id=2) == 2
