"""FastAPI routes for notifications + resubmit requests (FR-013, FR-018, FR-019).

Thin orchestration only — every piece of business logic lives in
:class:`app.domain.notifications.service.NotificationService` and
:class:`app.domain.notifications.resubmit.ResubmitRequestService`.

Batch 2 ships before (or in parallel with) ``app.core.security.rbac``, so
the RBAC dependency is imported optionally. When the real module is not
importable, ``require_role(...)`` becomes a permissive no-op; the real
dependency lands when M10 wires SSO/RBAC.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notifications.resubmit import ResubmitRequestService
from app.domain.notifications.service import NotificationService
from app.infra.db.session import get_session
from app.infra.email import EmailClient

# --- RBAC dependency stub -------------------------------------------------
# Batch 2 security wires this via ``app.core.security.rbac.require_role``.
try:  # pragma: no cover — exercised once M10 lands
    from app.core.security.rbac import Role, require_role  # type: ignore[import-not-found]
except ImportError:

    class Role:  # type: ignore[no-redef]
        """Batch 2 placeholder — M10 ships the real :class:`Role` enum."""

        FinanceAdmin = "FinanceAdmin"
        SystemAdmin = "SystemAdmin"
        UplineReviewer = "UplineReviewer"
        CompanyReviewer = "CompanyReviewer"

    def require_role(*_roles: Any) -> Callable[[], None]:  # type: ignore[no-redef]
        """Batch 2 placeholder RBAC dependency — M10 will wire real RBAC.

        Args:
            *_roles: Role names accepted by the real dependency (ignored
                here).

        Returns:
            Callable[[], None]: A no-op FastAPI dependency.
        """

        def _noop() -> None:
            """Allow the request through unconditionally (Batch 2 stub)."""
            return None

        return _noop


__all__ = [
    "FailedNotificationItem",
    "FailedNotificationList",
    "ResubmitRequestCreate",
    "ResubmitRequestRead",
    "router",
]


router = APIRouter(prefix="/notifications", tags=["notifications"])
resubmit_router = APIRouter(prefix="/resubmit-requests", tags=["notifications"])


# --------------------------------------------------------------------- schemas
class FailedNotificationItem(BaseModel):
    """Single item in the failed-notifications list response."""

    id: UUID
    type: str
    recipient_id: UUID
    status: str
    bounce_reason: str | None
    created_at: datetime


class FailedNotificationList(BaseModel):
    """Response body for ``GET /notifications/failed``."""

    items: list[FailedNotificationItem]


class ResendBody(BaseModel):
    """Request body for the resend endpoint."""

    recipient_email: str


class ResendResponse(BaseModel):
    """Response body for ``POST /notifications/{id}/resend``."""

    id: UUID
    status: str
    bounce_reason: str | None


class ResubmitRequestCreate(BaseModel):
    """Request body for creating a resubmit request."""

    cycle_id: UUID
    org_unit_id: UUID
    reason: str
    target_version: int | None = None
    requester_user_id: UUID
    recipient_user_id: UUID
    recipient_email: str


class ResubmitRequestRead(BaseModel):
    """Response body for a single resubmit request."""

    id: UUID
    cycle_id: UUID
    org_unit_id: UUID
    requester_id: UUID
    target_version: int | None
    reason: str
    requested_at: datetime


# -------------------------------------------------------------- notifications
def _build_notification_service(db: AsyncSession) -> NotificationService:
    """Construct a :class:`NotificationService` with the default email client.

    Kept as a helper so API tests can override it via FastAPI dependency
    overrides when they want to inject :class:`FakeSMTP`.

    Args:
        db: Active async session.

    Returns:
        NotificationService: Ready-to-use service bound to ``db``.
    """
    return NotificationService(db, email_client=EmailClient())


@router.get("/failed", response_model=FailedNotificationList)
async def list_failed_notifications(
    db: AsyncSession = Depends(get_session),
    _user: None = Depends(require_role(Role.FinanceAdmin, Role.SystemAdmin)),
) -> FailedNotificationList:
    """List notifications whose status is ``failed``.

    Args:
        db: Database session from FastAPI dependency.
        _user: RBAC guard (Batch 2 stub; M10 wires real RBAC).

    Returns:
        FailedNotificationList: Failed rows, newest first.
    """
    del _user
    service = _build_notification_service(db)
    rows = await service.list_failed()
    return FailedNotificationList(
        items=[
            FailedNotificationItem(
                id=r.id,
                type=r.type,
                recipient_id=r.recipient_id,
                status=r.status,
                bounce_reason=r.bounce_reason,
                created_at=r.created_at,
            )
            for r in rows
        ]
    )


@router.post("/{notification_id}/resend", response_model=ResendResponse)
async def resend_notification(
    notification_id: UUID,
    body: ResendBody,
    db: AsyncSession = Depends(get_session),
    _user: None = Depends(require_role(Role.FinanceAdmin, Role.SystemAdmin)),
) -> ResendResponse:
    """Resend a previously failed notification.

    Args:
        notification_id: UUID of the notification to resend.
        body: Resend request body (recipient email).
        db: Database session from FastAPI dependency.
        _user: RBAC guard (Batch 2 stub).

    Returns:
        ResendResponse: The updated row's status.
    """
    del _user
    service = _build_notification_service(db)
    notif = await service.resend(notification_id, recipient_email=body.recipient_email)
    await db.commit()
    return ResendResponse(
        id=notif.id,
        status=notif.status,
        bounce_reason=notif.bounce_reason,
    )


# --------------------------------------------------------- resubmit requests
@resubmit_router.post("", response_model=ResubmitRequestRead, status_code=201)
async def create_resubmit_request(
    body: ResubmitRequestCreate,
    db: AsyncSession = Depends(get_session),
    _user: None = Depends(
        require_role(
            Role.FinanceAdmin,
            Role.UplineReviewer,
            Role.CompanyReviewer,
        )
    ),
) -> ResubmitRequestRead:
    """Create a resubmit request and send the notification email.

    Args:
        body: Request body with cycle/org/reason/recipient details.
        db: Database session from FastAPI dependency.
        _user: RBAC guard (Batch 2 stub).

    Returns:
        ResubmitRequestRead: The persisted row.
    """
    del _user
    notif_service = _build_notification_service(db)
    service = ResubmitRequestService(db, notification_service=notif_service)
    rr = await service.create(
        cycle_id=body.cycle_id,
        org_unit_id=body.org_unit_id,
        requester_user_id=body.requester_user_id,
        reason=body.reason,
        recipient_user_id=body.recipient_user_id,
        recipient_email=body.recipient_email,
        target_version=body.target_version,
    )
    return ResubmitRequestRead(
        id=rr.id,
        cycle_id=rr.cycle_id,
        org_unit_id=rr.org_unit_id,
        requester_id=rr.requester_id,
        target_version=rr.target_version,
        reason=rr.reason,
        requested_at=rr.requested_at,
    )


@resubmit_router.get("", response_model=list[ResubmitRequestRead])
async def list_resubmit_requests(
    cycle_id: UUID,
    org_unit_id: UUID,
    db: AsyncSession = Depends(get_session),
    _user: None = Depends(
        require_role(
            Role.FinanceAdmin,
            Role.UplineReviewer,
            Role.CompanyReviewer,
        )
    ),
) -> list[ResubmitRequestRead]:
    """List resubmit requests for a (cycle, org unit) pair.

    Args:
        cycle_id: Target cycle UUID.
        org_unit_id: Target org unit UUID.
        db: Database session from FastAPI dependency.
        _user: RBAC guard (Batch 2 stub).

    Returns:
        list[ResubmitRequestRead]: Rows ordered by ``requested_at`` desc.
    """
    del _user
    notif_service = _build_notification_service(db)
    service = ResubmitRequestService(db, notification_service=notif_service)
    rows = await service.list(cycle_id, org_unit_id)
    return [
        ResubmitRequestRead(
            id=r.id,
            cycle_id=r.cycle_id,
            org_unit_id=r.org_unit_id,
            requester_id=r.requester_id,
            target_version=r.target_version,
            reason=r.reason,
            requested_at=r.requested_at,
        )
        for r in rows
    ]
