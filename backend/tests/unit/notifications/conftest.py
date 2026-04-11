"""Shared fixtures for :mod:`app.domain.notifications` unit tests.

Like the audit unit tier, these tests substitute the real
:class:`NotificationRepo` with an in-memory fake that implements the
same async surface. This is NOT cross-module mocking — the fake is a
test-owned repo double that exercises the real
:class:`NotificationService` and the real template dispatch path.

Real Postgres round-trips live in
``tests/integration/notifications/test_notifications_integration.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_utc
from app.domain.audit.actions import AuditAction
from app.domain.notifications.models import Notification, ResubmitRequest
from app.infra.email import FakeSMTP

__all__ = [
    "FakeAuditService",
    "InMemoryNotificationRepo",
    "RecordingSession",
    "audit_service",
    "fake_repo",
    "fake_session",
    "fake_smtp",
    "notification_service",
    "resubmit_service",
]


class InMemoryNotificationRepo:
    """In-memory stand-in for :class:`NotificationRepo`.

    Implements the same async methods used by
    :class:`NotificationService` and
    :class:`ResubmitRequestService`. Rows live in ``notifications`` and
    ``resubmits`` lists; ``insert`` assigns an id and a ``created_at``
    timestamp so the service sees the same shape it would with a real
    flush.
    """

    def __init__(self) -> None:
        """Initialize empty stores."""
        self.notifications: list[Notification] = []
        self.resubmits: list[ResubmitRequest] = []
        self.fail_next_resubmit_insert: bool = False

    async def insert(self, notif: Notification) -> Notification:
        """Assign an id (if missing) and append to the store."""
        if getattr(notif, "id", None) is None:
            notif.id = uuid4()
        if getattr(notif, "created_at", None) is None:
            notif.created_at = now_utc()
        self.notifications.append(notif)
        return notif

    async def get(self, notif_id: UUID) -> Notification | None:
        """Return the row with ``id == notif_id``, or ``None``."""
        for n in self.notifications:
            if n.id == notif_id:
                return n
        return None

    async def mark_sent(self, notif_id: UUID, sent_at: datetime) -> None:
        """Flip the row to ``status=sent``."""
        notif = await self.get(notif_id)
        if notif is None:
            return
        notif.status = "sent"
        notif.sent_at = sent_at
        notif.bounce_reason = None

    async def mark_failed(self, notif_id: UUID, error: str) -> None:
        """Flip the row to ``status=failed`` with ``error`` as reason."""
        notif = await self.get(notif_id)
        if notif is None:
            return
        notif.status = "failed"
        notif.bounce_reason = error

    async def list_failed(self, limit: int = 100) -> list[Notification]:
        """Return failed rows sorted newest-first."""
        failed = [n for n in self.notifications if n.status == "failed"]
        failed.sort(key=lambda n: n.created_at, reverse=True)
        return failed[:limit]

    async def insert_resubmit(self, rr: ResubmitRequest) -> ResubmitRequest:
        """Append a resubmit row; optionally raise for failure-injection."""
        if self.fail_next_resubmit_insert:
            self.fail_next_resubmit_insert = False
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError("INSERT resubmit_requests", {}, Exception("boom"))
        if getattr(rr, "id", None) is None:
            rr.id = uuid4()
        if getattr(rr, "requested_at", None) is None:
            rr.requested_at = now_utc()
        self.resubmits.append(rr)
        return rr

    async def list_resubmits(
        self,
        cycle_id: UUID,
        org_unit_id: UUID,
    ) -> list[ResubmitRequest]:
        """Return matching resubmit rows, newest first."""
        matching = [
            r for r in self.resubmits if r.cycle_id == cycle_id and r.org_unit_id == org_unit_id
        ]
        matching.sort(key=lambda r: r.requested_at, reverse=True)
        return matching


class RecordingSession:
    """Minimal :class:`AsyncSession` stand-in tracking commit/rollback calls.

    The notification + resubmit services call ``commit`` and ``rollback``
    directly on the session; this double records both without needing a
    real engine.
    """

    def __init__(self) -> None:
        """Initialize counters."""
        self.commits: int = 0
        self.rollbacks: int = 0
        self.flushes: int = 0

    async def commit(self) -> None:
        """Record a commit."""
        self.commits += 1

    async def rollback(self) -> None:
        """Record a rollback."""
        self.rollbacks += 1

    async def flush(self) -> None:
        """Record a flush (no-op)."""
        self.flushes += 1

    def add(self, _obj: Any) -> None:
        """No-op add — the fake repo owns the stores."""
        return None


class FakeAuditService:
    """In-memory stand-in for :class:`AuditService`.

    Records every call to :meth:`record` so tests can assert on the
    action verb, resource type, and details payload without needing the
    real hash-chain machinery.
    """

    def __init__(self) -> None:
        """Initialize an empty event log."""
        self.events: list[dict[str, Any]] = []

    async def record(
        self,
        *,
        action: AuditAction,
        resource_type: str,
        resource_id: UUID | None = None,
        user_id: UUID | None = None,
        ip_address: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record an audit call to :attr:`events`."""
        self.events.append(
            {
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "user_id": user_id,
                "ip_address": ip_address,
                "details": dict(details) if details else {},
            }
        )


@pytest.fixture
def fake_repo() -> InMemoryNotificationRepo:
    """Fresh per-test in-memory repo."""
    return InMemoryNotificationRepo()


@pytest.fixture
def fake_session() -> RecordingSession:
    """Fresh recording session double."""
    return RecordingSession()


@pytest.fixture
def fake_smtp() -> FakeSMTP:
    """Fresh :class:`FakeSMTP` instance (from ``infra.email``)."""
    return FakeSMTP()


@pytest.fixture
def audit_service() -> FakeAuditService:
    """Fresh :class:`FakeAuditService`."""
    return FakeAuditService()


@pytest_asyncio.fixture
async def notification_service(
    fake_session: RecordingSession,
    fake_repo: InMemoryNotificationRepo,
    fake_smtp: FakeSMTP,
    audit_service: FakeAuditService,
) -> AsyncIterator[Any]:
    """Yield a :class:`NotificationService` wired to the fakes.

    The real service class is constructed with a ``MagicMock`` session
    (for the typed :class:`AsyncSession` parameter) and then has its
    private ``_repo`` / ``_audit`` attributes swapped for the fakes.
    """
    from app.domain.notifications.service import NotificationService

    session_mock = MagicMock(spec=AsyncSession)
    session_mock.commit = fake_session.commit
    session_mock.rollback = fake_session.rollback
    session_mock.flush = fake_session.flush
    session_mock.add = fake_session.add

    service = NotificationService(session_mock, email_client=fake_smtp)
    service._repo = fake_repo  # type: ignore[assignment]
    service._audit = audit_service  # type: ignore[assignment]
    yield service


@pytest_asyncio.fixture
async def resubmit_service(
    fake_session: RecordingSession,
    fake_repo: InMemoryNotificationRepo,
    fake_smtp: FakeSMTP,
    audit_service: FakeAuditService,
    notification_service: Any,
) -> AsyncIterator[Any]:
    """Yield a :class:`ResubmitRequestService` wired to the fakes."""
    from app.domain.notifications.resubmit import ResubmitRequestService

    session_mock = MagicMock(spec=AsyncSession)
    session_mock.commit = fake_session.commit
    session_mock.rollback = fake_session.rollback
    session_mock.flush = fake_session.flush
    session_mock.add = fake_session.add

    service = ResubmitRequestService(
        session_mock,
        notification_service=notification_service,
        audit_service=audit_service,  # type: ignore[arg-type]
    )
    service._repo = fake_repo  # type: ignore[assignment]
    yield service
