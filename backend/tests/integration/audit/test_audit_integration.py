"""Integration tests for :mod:`app.domain.audit` against live Postgres.

Requires a reachable Postgres (see ``tests/integration/conftest.py``).
Tests are skipped when no database is configured so that the unit tier
can run on a workstation without Docker.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.domain.audit.actions import AuditAction
from app.domain.audit.repo import AuditFilters, AuditRepo
from app.domain.audit.service import AuditService
from tests.integration.conftest import skip_unless_postgres

pytestmark = [skip_unless_postgres, pytest.mark.integration]


async def _truncate_audit(session: AsyncSession) -> None:
    """Reset the audit_logs table and its sequence before each test."""
    await session.execute(text("TRUNCATE TABLE audit_logs RESTART IDENTITY CASCADE"))
    await session.commit()


async def test_record_round_trip(db_session: AsyncSession) -> None:
    """Five records land in the DB with sequential sequence numbers."""
    await _truncate_audit(db_session)
    service = AuditService(db_session)
    rows = []
    for i in range(5):
        row = await service.record(
            action=AuditAction.CYCLE_OPEN,
            resource_type="cycle",
            details={"i": i},
        )
        rows.append(row)
    await db_session.commit()

    sequence_nos = [r.sequence_no for r in rows]
    assert sequence_nos == sorted(sequence_nos)
    assert len(set(sequence_nos)) == 5

    result = await service.verify_chain(None, None)
    assert result.verified is True
    assert result.chain_length == 5


async def test_verify_chain_detects_tampered_row(db_session: AsyncSession) -> None:
    """Raw-SQL UPDATE of ``details`` trips ``verify_chain`` with AUDIT_001.

    Audit rows are normally protected by ``REVOKE UPDATE`` — the test
    runs as a DB owner/superuser so the UPDATE succeeds, simulating an
    attacker with elevated access.
    """
    await _truncate_audit(db_session)
    service = AuditService(db_session)
    for i in range(3):
        await service.record(
            action=AuditAction.CYCLE_OPEN,
            resource_type="cycle",
            details={"i": i},
        )
    await db_session.commit()

    try:
        await db_session.execute(
            text(
                "UPDATE audit_logs SET details = :d WHERE sequence_no = "
                "(SELECT sequence_no FROM audit_logs ORDER BY sequence_no LIMIT 1 OFFSET 1)"
            ),
            {"d": '{"tampered": true}'},
        )
        await db_session.commit()
    except Exception:
        pytest.skip("Test role lacks UPDATE privilege on audit_logs")

    fresh_service = AuditService(db_session)
    with pytest.raises(AppError) as exc_info:
        await fresh_service.verify_chain(None, None)
    assert exc_info.value.code == "AUDIT_001"


async def test_fetch_page_filters(db_session: AsyncSession) -> None:
    """The repo's filtered page matches the rows inserted via the service."""
    await _truncate_audit(db_session)
    service = AuditService(db_session)
    await service.record(action=AuditAction.LOGIN_SUCCESS, resource_type="session", details={})
    await service.record(action=AuditAction.LOGOUT, resource_type="session", details={})
    await db_session.commit()

    repo = AuditRepo(db_session)
    result = await repo.fetch_page(AuditFilters(action="LOGIN_SUCCESS"))
    assert result.total == 1
    assert result.items[0].action == "LOGIN_SUCCESS"


async def test_get_latest_empty_table_returns_none(db_session: AsyncSession) -> None:
    """An empty ``audit_logs`` table produces ``None`` from ``get_latest``."""
    await _truncate_audit(db_session)
    repo = AuditRepo(db_session)
    latest = await repo.get_latest()
    assert latest is None
