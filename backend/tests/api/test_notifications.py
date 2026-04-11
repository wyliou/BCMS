"""API-level smoke tests for :mod:`app.api.v1.notifications`.

RBAC enforcement is deferred to Batch 2 / M10 — every 403-style test is
marked ``skip`` until the real RBAC dependency lands. The remaining
tests use FastAPI's ``dependency_overrides`` to inject the in-memory
notification and resubmit services exercised in the unit tier.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.notifications import (
    resubmit_router,
)
from app.api.v1.notifications import (
    router as notifications_router,
)
from app.domain.notifications.models import Notification
from app.infra.db.session import get_session
from app.infra.email import FakeSMTP


class _FakeSession:
    """Minimal async session stand-in used by the API smoke tests."""

    def __init__(self) -> None:
        """Initialize counters used by the services."""
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        """Record a commit."""
        self.commits += 1

    async def rollback(self) -> None:
        """Record a rollback."""
        self.rollbacks += 1

    async def flush(self) -> None:
        """No-op flush."""
        return None

    def add(self, _obj: Any) -> None:
        """No-op add — the fake repo owns storage."""
        return None


@pytest.fixture
def notification_app() -> FastAPI:
    """Build a FastAPI app with both notification routers mounted.

    Overrides :func:`get_session` so every request sees the same fake
    session. The real :class:`NotificationService` and
    :class:`ResubmitRequestService` are constructed per request by the
    route handlers and then have their ``_repo`` / ``_email`` /
    ``_audit`` attributes swapped for fakes via a patch on the
    constructor helper.
    """
    from unittest.mock import MagicMock, patch

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.domain.notifications.repo import NotificationRepo
    from app.domain.notifications.service import NotificationService
    from tests.unit.notifications.conftest import (
        FakeAuditService,
        InMemoryNotificationRepo,
    )

    application = FastAPI()
    application.include_router(notifications_router, prefix="/api/v1")
    application.include_router(resubmit_router, prefix="/api/v1")

    shared_repo = InMemoryNotificationRepo()
    shared_audit = FakeAuditService()
    shared_smtp = FakeSMTP()

    async def _override_session() -> AsyncIterator[Any]:
        yield _FakeSession()

    # Patch the helper in the module that the route handlers import from.
    def _patched_builder(db: Any) -> NotificationService:
        service = NotificationService(
            MagicMock(spec=AsyncSession),
            email_client=shared_smtp,
        )
        service._repo = shared_repo  # type: ignore[assignment]
        service._audit = shared_audit  # type: ignore[assignment]
        return service

    # Also patch NotificationRepo used indirectly by ResubmitRequestService.
    original_repo_init = NotificationRepo.__init__

    def _patched_repo_init(self: NotificationRepo, db: Any) -> None:
        original_repo_init(self, db)
        # Swap all lookups to go through the shared fake repo.
        self.insert = shared_repo.insert  # type: ignore[method-assign]
        self.insert_resubmit = shared_repo.insert_resubmit  # type: ignore[method-assign]
        self.get = shared_repo.get  # type: ignore[method-assign]
        self.mark_sent = shared_repo.mark_sent  # type: ignore[method-assign]
        self.mark_failed = shared_repo.mark_failed  # type: ignore[method-assign]
        self.list_failed = shared_repo.list_failed  # type: ignore[method-assign]
        self.list_resubmits = shared_repo.list_resubmits  # type: ignore[method-assign]

    NotificationRepo.__init__ = _patched_repo_init  # type: ignore[method-assign]

    patch_target = "app.api.v1.notifications._build_notification_service"
    patcher = patch(patch_target, new=_patched_builder)
    patcher.start()
    application.state._notifications_patcher = patcher  # type: ignore[attr-defined]
    application.state._shared_repo = shared_repo  # type: ignore[attr-defined]
    application.state._shared_smtp = shared_smtp  # type: ignore[attr-defined]
    application.state._original_repo_init = original_repo_init  # type: ignore[attr-defined]
    application.dependency_overrides[get_session] = _override_session
    return application


@pytest.fixture
async def client(notification_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Yield an :class:`httpx.AsyncClient` wired to the notification app."""
    transport = httpx.ASGITransport(app=notification_app, raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    notification_app.state._notifications_patcher.stop()  # type: ignore[attr-defined]
    # Restore the real repo __init__ so other test files are unaffected.
    from app.domain.notifications.repo import NotificationRepo

    NotificationRepo.__init__ = notification_app.state._original_repo_init  # type: ignore[method-assign]


# ------------------------------------------------------------------- tests
async def test_list_failed_returns_empty_list_by_default(
    client: httpx.AsyncClient,
) -> None:
    """GET /notifications/failed returns an empty list when no rows exist."""
    response = await client.get("/api/v1/notifications/failed")
    assert response.status_code == 200, response.text
    assert response.json() == {"items": []}


async def test_list_failed_returns_seeded_failed_rows(
    client: httpx.AsyncClient,
    notification_app: FastAPI,
) -> None:
    """GET /notifications/failed surfaces seeded failed rows."""
    from app.core.clock import now_utc

    shared_repo = notification_app.state._shared_repo  # type: ignore[attr-defined]
    row = Notification(
        recipient_id=uuid4(),
        type="upload_confirmed",
        channel="email",
        status="failed",
        bounce_reason="SMTP relay unreachable",
        created_at=now_utc(),
    )
    row.id = uuid4()
    shared_repo.notifications.append(row)

    response = await client.get("/api/v1/notifications/failed")
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["bounce_reason"] == "SMTP relay unreachable"


async def test_resend_notification_flips_status_to_sent(
    client: httpx.AsyncClient,
    notification_app: FastAPI,
) -> None:
    """POST /notifications/{id}/resend delivers and flips status."""
    from app.core.clock import now_utc

    shared_repo = notification_app.state._shared_repo  # type: ignore[attr-defined]
    row = Notification(
        recipient_id=uuid4(),
        type="upload_confirmed",
        channel="email",
        status="failed",
        bounce_reason="previous failure",
        created_at=now_utc(),
    )
    row.id = uuid4()
    shared_repo.notifications.append(row)

    response = await client.post(
        f"/api/v1/notifications/{row.id}/resend",
        json={"recipient_email": "alice@example.invalid"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "sent"


async def test_create_resubmit_request_returns_201(
    client: httpx.AsyncClient,
) -> None:
    """POST /resubmit-requests persists and returns 201."""
    payload = {
        "cycle_id": str(uuid4()),
        "org_unit_id": str(uuid4()),
        "reason": "please resubmit",
        "target_version": 2,
        "requester_user_id": str(uuid4()),
        "recipient_user_id": str(uuid4()),
        "recipient_email": "manager@example.invalid",
    }
    response = await client.post("/api/v1/resubmit-requests", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["cycle_id"] == payload["cycle_id"]
    assert body["reason"] == "please resubmit"


@pytest.mark.skip(reason="RBAC enforcement wired in Batch 2 / M10")
async def test_list_failed_requires_finance_admin() -> None:
    """GET as FilingUnitManager returns 403 once RBAC is wired."""


@pytest.mark.skip(reason="RBAC enforcement wired in Batch 2 / M10")
async def test_create_resubmit_invalid_requester_role() -> None:
    """POST as FilingUnitManager returns 403 once RBAC is wired."""
