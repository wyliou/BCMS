"""Integration tests for notifications + resubmit requests (requires Postgres).

Exercises a real DB round-trip through :class:`NotificationRepo`: inserts
a notification row, transitions it through ``queued -> sent``, reads it
back, and then inserts + lists a resubmit request. Rolled back at
teardown so the baseline remains clean.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_utc
from app.domain.notifications.models import Notification, ResubmitRequest
from app.domain.notifications.repo import NotificationRepo
from tests.integration.conftest import skip_unless_postgres

pytestmark = [pytest.mark.integration, skip_unless_postgres]


async def _seed_cycle_and_org(db: AsyncSession) -> tuple:
    """Insert a throwaway org_unit, user, and cycle; return their IDs."""
    org_id = uuid4()
    cycle_id = uuid4()
    user_id = uuid4()
    await db.execute(
        text(
            "INSERT INTO org_units (id, code, name, level_code) "
            "VALUES (:id, :code, :name, '0000')"
        ),
        {"id": org_id, "code": f"T{str(org_id)[:6]}", "name": "int-test-org"},
    )
    await db.execute(
        text(
            "INSERT INTO users (id, email, full_name, roles, org_unit_id) "
            "VALUES (:id, :email, 'Test User', ARRAY['FinanceAdmin']::text[], :org_id)"
        ),
        {"id": user_id, "email": f"{user_id}@example.invalid", "org_id": org_id},
    )
    await db.execute(
        text(
            "INSERT INTO budget_cycles (id, fiscal_year, status, created_by) "
            "VALUES (:id, :fy, 'draft', :uid)"
        ),
        {"id": cycle_id, "fy": 2099, "uid": user_id},
    )
    return org_id, cycle_id, user_id


async def test_notification_roundtrip(db_session: AsyncSession) -> None:
    """Insert, mark sent, read back a notification row."""
    _, _, user_id = await _seed_cycle_and_org(db_session)
    repo = NotificationRepo(db_session)

    notif = Notification(
        recipient_id=user_id,
        type="upload_confirmed",
        channel="email",
        status="queued",
        created_at=now_utc(),
    )
    await repo.insert(notif)
    assert notif.id is not None

    await repo.mark_sent(notif.id, now_utc())
    fetched = await repo.get(notif.id)
    assert fetched is not None
    assert fetched.status == "sent"
    assert fetched.sent_at is not None


async def test_resubmit_request_roundtrip(db_session: AsyncSession) -> None:
    """Insert and list a resubmit request."""
    org_id, cycle_id, user_id = await _seed_cycle_and_org(db_session)
    repo = NotificationRepo(db_session)

    rr = ResubmitRequest(
        cycle_id=cycle_id,
        org_unit_id=org_id,
        requester_id=user_id,
        reason="integration test",
        target_version=1,
        requested_at=now_utc(),
    )
    await repo.insert_resubmit(rr)
    assert rr.id is not None

    rows = await repo.list_resubmits(cycle_id, org_id)
    assert len(rows) == 1
    assert rows[0].reason == "integration test"
