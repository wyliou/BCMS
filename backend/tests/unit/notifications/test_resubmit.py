"""Unit tests for :class:`ResubmitRequestService`.

Focuses on the CR-007 / FR-019 lock: the resubmit row must be written +
committed BEFORE the notification email is dispatched. If the row write
fails, the email must NOT be sent and the service must raise
``NOTIFY_002``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.domain.audit.actions import AuditAction
from app.domain.notifications.resubmit import ResubmitRequestService
from app.infra.email import FakeSMTP

from .conftest import FakeAuditService, InMemoryNotificationRepo, RecordingSession


async def test_create_resubmit_happy_path(
    resubmit_service: ResubmitRequestService,
    fake_repo: InMemoryNotificationRepo,
    fake_smtp: FakeSMTP,
    fake_session: RecordingSession,
    audit_service: FakeAuditService,
) -> None:
    """Row inserted + committed + email sent + audit recorded."""
    cycle_id = uuid4()
    org_id = uuid4()
    requester_id = uuid4()
    recipient_id = uuid4()

    rr = await resubmit_service.create(
        cycle_id=cycle_id,
        org_unit_id=org_id,
        requester_user_id=requester_id,
        reason="Row 42 has a negative amount",
        recipient_user_id=recipient_id,
        recipient_email="manager@example.invalid",
        target_version=3,
        context_extra={
            "cycle_fiscal_year": 2026,
            "org_unit_name": "Finance-HQ",
            "template_url": "https://bcms/templates/abc",
        },
    )

    assert rr.cycle_id == cycle_id
    assert rr.org_unit_id == org_id
    assert len(fake_repo.resubmits) == 1
    assert len(fake_smtp.sent) == 1
    assert fake_smtp.sent[0].template == "resubmit_requested"
    # Two commits: one after resubmit insert, one after final audit record.
    assert fake_session.commits >= 1
    # A RESUBMIT_REQUEST audit entry was recorded.
    actions = [ev["action"] for ev in audit_service.events]
    assert AuditAction.RESUBMIT_REQUEST in actions


async def test_create_resubmit_db_failure_raises_notify_002_and_no_email(
    resubmit_service: ResubmitRequestService,
    fake_repo: InMemoryNotificationRepo,
    fake_smtp: FakeSMTP,
    fake_session: RecordingSession,
) -> None:
    """CR-007: row write failure raises NOTIFY_002 and no email is sent."""
    fake_repo.fail_next_resubmit_insert = True

    with pytest.raises(AppError) as exc_info:
        await resubmit_service.create(
            cycle_id=uuid4(),
            org_unit_id=uuid4(),
            requester_user_id=uuid4(),
            reason="boom",
            recipient_user_id=uuid4(),
            recipient_email="manager@example.invalid",
        )
    assert exc_info.value.code == "NOTIFY_002"
    assert len(fake_smtp.sent) == 0, "Email must not be sent when row write fails"
    assert fake_session.rollbacks >= 1


async def test_create_resubmit_email_failure_record_still_valid(
    resubmit_service: ResubmitRequestService,
    fake_repo: InMemoryNotificationRepo,
    fake_smtp: FakeSMTP,
) -> None:
    """CR-029: email failure leaves the resubmit row valid and returned."""
    fake_smtp.should_fail = True

    rr = await resubmit_service.create(
        cycle_id=uuid4(),
        org_unit_id=uuid4(),
        requester_user_id=uuid4(),
        reason="r",
        recipient_user_id=uuid4(),
        recipient_email="manager@example.invalid",
        context_extra={
            "cycle_fiscal_year": 2026,
            "org_unit_name": "X",
            "template_url": "x",
        },
    )
    assert rr is not None
    assert len(fake_repo.resubmits) == 1
    # Notification row exists and was marked failed.
    assert len(fake_repo.notifications) == 1
    assert fake_repo.notifications[0].status == "failed"


async def test_list_resubmit_requests_orders_newest_first(
    resubmit_service: ResubmitRequestService,
    fake_repo: InMemoryNotificationRepo,
) -> None:
    """list() returns all matching rows sorted by ``requested_at`` desc."""
    from datetime import datetime, timedelta, timezone

    from app.domain.notifications.models import ResubmitRequest

    cycle_id = uuid4()
    org_id = uuid4()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(3):
        rr = ResubmitRequest(
            cycle_id=cycle_id,
            org_unit_id=org_id,
            requester_id=uuid4(),
            target_version=None,
            reason=f"r{i}",
            requested_at=base + timedelta(days=i),
        )
        rr.id = uuid4()
        fake_repo.resubmits.append(rr)

    rows = await resubmit_service.list(cycle_id, org_id)
    assert len(rows) == 3
    assert rows[0].reason == "r2"
    assert rows[-1].reason == "r0"
