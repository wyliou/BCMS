"""Integration tests for :mod:`app.infra.jobs` (requires Postgres)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra import jobs as jobs_module
from tests.integration.conftest import skip_unless_postgres

pytestmark = [pytest.mark.integration, skip_unless_postgres]


@pytest.fixture(autouse=True)
def _clear_handlers() -> Iterator[None]:
    """Ensure the handler registry is clean between tests."""
    jobs_module.unregister_all_handlers()
    yield
    jobs_module.unregister_all_handlers()


async def test_enqueue_unknown_type_raises(db_session: AsyncSession) -> None:
    """Enqueueing an unregistered job type raises ``ValueError``."""
    with pytest.raises(ValueError):
        await jobs_module.enqueue("nope", {}, db=db_session)


async def test_enqueue_creates_row(db_session: AsyncSession) -> None:
    """``enqueue`` inserts a new ``job_runs`` row."""

    async def _handler(payload: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "echo": payload}

    jobs_module.register_handler("noop", _handler)
    job_id = await jobs_module.enqueue("noop", {"a": 1}, db=db_session)
    await db_session.commit()
    status = await jobs_module.get_status(job_id, db=db_session)
    assert status["status"] == "queued"
    assert status["job_type"] == "noop"
