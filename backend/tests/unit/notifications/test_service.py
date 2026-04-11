"""Unit tests for :class:`app.domain.notifications.service.NotificationService`.

Uses the in-memory fakes from ``conftest.py``:

* :class:`InMemoryNotificationRepo` for the row store.
* :class:`FakeSMTP` (from ``infra.email``) for the email client.
* :class:`FakeAuditService` for audit capture.

CR-029 is exercised by :func:`test_send_smtp_failure_does_not_raise` and
:func:`test_send_batch_partial_failure`.
"""

from __future__ import annotations

from uuid import uuid4

from app.domain.audit.actions import AuditAction
from app.domain.notifications.service import NotificationService
from app.domain.notifications.templates import NotificationTemplate
from app.infra.email import FakeSMTP

from .conftest import FakeAuditService, InMemoryNotificationRepo


async def test_send_success_marks_row_sent_and_audits(
    notification_service: NotificationService,
    fake_repo: InMemoryNotificationRepo,
    fake_smtp: FakeSMTP,
    audit_service: FakeAuditService,
) -> None:
    """Happy path: row inserted, marked sent, audit event recorded."""
    user_id = uuid4()
    notif = await notification_service.send(
        template=NotificationTemplate.UPLOAD_CONFIRMED,
        recipient_user_id=user_id,
        recipient_email="alice@example.invalid",
        context={
            "org_unit_name": "Finance-HQ",
            "version": 1,
            "filename": "budget.xlsx",
            "uploaded_at": "2026-01-01T00:00:00Z",
            "upload_url": "https://bcms/abc",
        },
    )

    assert notif.status == "sent"
    assert notif.sent_at is not None
    assert len(fake_repo.notifications) == 1
    assert len(fake_smtp.sent) == 1
    assert fake_smtp.sent[0].template == "upload_confirmed"
    assert fake_smtp.sent[0].recipient == "alice@example.invalid"
    # Exactly one audit entry with NOTIFY_SENT.
    assert len(audit_service.events) == 1
    assert audit_service.events[0]["action"] == AuditAction.NOTIFY_SENT
    assert audit_service.events[0]["resource_type"] == "notification"


async def test_send_smtp_failure_does_not_raise(
    notification_service: NotificationService,
    fake_repo: InMemoryNotificationRepo,
    fake_smtp: FakeSMTP,
    audit_service: FakeAuditService,
) -> None:
    """CR-029: SMTP failure marks row failed and returns normally."""
    fake_smtp.should_fail = True

    notif = await notification_service.send(
        template=NotificationTemplate.CYCLE_OPENED,
        recipient_user_id=uuid4(),
        recipient_email="bob@example.invalid",
        context={"cycle_fiscal_year": 2026, "deadline": "x", "cycle_url": "x"},
    )

    assert notif.status == "failed"
    assert notif.bounce_reason is not None
    assert fake_repo.notifications[0].status == "failed"
    # Exactly one NOTIFY_FAILED audit entry; no NOTIFY_SENT.
    assert len(audit_service.events) == 1
    assert audit_service.events[0]["action"] == AuditAction.NOTIFY_FAILED


async def test_send_batch_partial_failure_returns_mixed(
    notification_service: NotificationService,
    fake_smtp: FakeSMTP,
    fake_repo: InMemoryNotificationRepo,
) -> None:
    """send_batch attempts each recipient; partial failures are reported."""
    # Reason: flip should_fail between recipients so the second send errors.
    original_send = fake_smtp.send
    call_count = {"n": 0}

    async def _toggle_send(*args: object, **kwargs: object) -> object:
        call_count["n"] += 1
        fake_smtp.should_fail = call_count["n"] == 2
        return await original_send(*args, **kwargs)  # type: ignore[arg-type]

    fake_smtp.send = _toggle_send  # type: ignore[method-assign]

    recipients = [
        (uuid4(), "a@example.invalid"),
        (uuid4(), "b@example.invalid"),
        (uuid4(), "c@example.invalid"),
    ]
    results = await notification_service.send_batch(
        template=NotificationTemplate.DEADLINE_REMINDER,
        recipients=recipients,
        context={
            "cycle_fiscal_year": 2026,
            "deadline": "2026-02-28",
            "days_remaining": 3,
            "upload_url": "https://bcms/abc",
        },
    )
    assert len(results) == 3
    statuses = [r.status for r in results]
    assert statuses == ["sent", "failed", "sent"]
    assert len(fake_repo.notifications) == 3


async def test_list_failed_returns_only_failed_rows(
    notification_service: NotificationService,
    fake_smtp: FakeSMTP,
) -> None:
    """list_failed filters to ``status=failed`` rows only."""
    # One success.
    await notification_service.send(
        template=NotificationTemplate.PERSONNEL_IMPORTED,
        recipient_user_id=uuid4(),
        recipient_email="ok@example.invalid",
        context={"fiscal_year": 2026, "uploader_name": "u", "affected_count": 1},
    )
    # Two failures.
    fake_smtp.should_fail = True
    await notification_service.send(
        template=NotificationTemplate.PERSONNEL_IMPORTED,
        recipient_user_id=uuid4(),
        recipient_email="err1@example.invalid",
        context={"fiscal_year": 2026, "uploader_name": "u", "affected_count": 1},
    )
    await notification_service.send(
        template=NotificationTemplate.PERSONNEL_IMPORTED,
        recipient_user_id=uuid4(),
        recipient_email="err2@example.invalid",
        context={"fiscal_year": 2026, "uploader_name": "u", "affected_count": 1},
    )

    failed = await notification_service.list_failed()
    assert len(failed) == 2
    assert all(n.status == "failed" for n in failed)


async def test_resend_failed_notification_flips_to_sent(
    notification_service: NotificationService,
    fake_smtp: FakeSMTP,
    audit_service: FakeAuditService,
) -> None:
    """resend() re-delivers a previously failed row and audits NOTIFY_RESENT."""
    # Seed one failed row via a normal send.
    fake_smtp.should_fail = True
    failed = await notification_service.send(
        template=NotificationTemplate.UPLOAD_CONFIRMED,
        recipient_user_id=uuid4(),
        recipient_email="alice@example.invalid",
        context={
            "org_unit_name": "X",
            "version": 1,
            "filename": "x",
            "uploaded_at": "x",
            "upload_url": "x",
        },
    )
    assert failed.status == "failed"
    audit_service.events.clear()

    # Allow the next call to succeed.
    fake_smtp.should_fail = False
    resent = await notification_service.resend(
        failed.id,
        recipient_email="alice@example.invalid",
    )
    assert resent.status == "sent"
    assert resent.sent_at is not None
    # One resend audit event.
    assert any(ev["action"] == AuditAction.NOTIFY_RESENT for ev in audit_service.events)
