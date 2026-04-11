"""Resubmit-request service (FR-018, FR-019).

Owns **CR-007**: the ``resubmit_requests`` row MUST be written and
committed before the resubmit notification email is dispatched. If the
row write fails the service raises :class:`AppError` with code
``NOTIFY_002`` and never calls the email client. If the row write
succeeds but the email fails, the row remains valid — per **CR-029** the
underlying :class:`NotificationService.send` marks the notification row
``failed`` and returns normally, and this service returns the
:class:`ResubmitRequest` as successful.

Audit recording follows **CR-006**: the row is committed first, then the
``RESUBMIT_REQUEST`` audit entry is written.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService
from app.domain.notifications.models import ResubmitRequest
from app.domain.notifications.repo import NotificationRepo
from app.domain.notifications.service import NotificationService
from app.domain.notifications.templates import NotificationTemplate

__all__ = ["ResubmitRequestService"]


_LOG = structlog.get_logger(__name__)


class ResubmitRequestService:
    """Create and list resubmit requests.

    Dependencies are injected explicitly so tests can wire
    :class:`FakeSMTP` (via :class:`NotificationService`) without touching
    module-level globals.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        notification_service: NotificationService,
        audit_service: AuditService | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            db: Active async session managed by the caller.
            notification_service: Downstream service used to send the
                resubmit email after the row is committed.
            audit_service: Optional audit service. Defaults to a new
                :class:`AuditService` bound to ``db``.
        """
        self._db = db
        self._repo = NotificationRepo(db)
        self._notifications = notification_service
        self._audit = audit_service if audit_service is not None else AuditService(db)

    async def create(
        self,
        *,
        cycle_id: UUID,
        org_unit_id: UUID,
        requester_user_id: UUID,
        reason: str,
        recipient_user_id: UUID,
        recipient_email: str,
        target_version: int | None = None,
        context_extra: dict[str, object] | None = None,
    ) -> ResubmitRequest:
        """Create a resubmit request row and dispatch the notification.

        Call order (LOCKED by CR-007 / FR-019):

        1. Insert the ``resubmit_requests`` row.
        2. ``await db.commit()`` — on failure raise ``NOTIFY_002``.
        3. Call :meth:`NotificationService.send`.
        4. Record the ``RESUBMIT_REQUEST`` audit entry (CR-006).

        The recipient is supplied by the caller because the org-tree
        walker that resolves filing-unit managers lives in
        :mod:`app.domain.cycles`, which ships in Batch 4. Batch 2 wires
        the API layer to pass ``recipient_email`` through verbatim.

        Args:
            cycle_id: Target cycle UUID.
            org_unit_id: Target org unit UUID.
            requester_user_id: UUID of the user making the request.
            reason: Human-readable explanation, stored verbatim.
            recipient_user_id: UUID of the manager who should receive
                the notification email.
            recipient_email: Plaintext email address for the recipient.
            target_version: Optional specific upload version to resubmit.
            context_extra: Optional additional template context (e.g.
                ``org_unit_name``, ``cycle_fiscal_year``). Merged into
                the notification context below the required keys.

        Returns:
            ResubmitRequest: The persisted row. Valid even when the
            downstream email send failed (CR-029).

        Raises:
            AppError: ``NOTIFY_002`` when the row write or commit fails;
                no notification is sent in this path.
        """
        rr = ResubmitRequest(
            cycle_id=cycle_id,
            org_unit_id=org_unit_id,
            requester_id=requester_user_id,
            target_version=target_version,
            reason=reason,
        )

        try:
            await self._repo.insert_resubmit(rr)
            await self._db.commit()
        except SQLAlchemyError as exc:
            _LOG.warning(
                "resubmit.insert_failed",
                cycle_id=str(cycle_id),
                org_unit_id=str(org_unit_id),
                error=str(exc),
            )
            await self._db.rollback()
            raise AppError(
                "NOTIFY_002",
                f"Failed to persist resubmit request: {exc}",
            ) from exc

        # CR-007 checkpoint: row is committed. Everything below may fail
        # without invalidating the resubmit record.
        context: dict[str, object] = {
            "reason": reason,
            "requested_by": str(requester_user_id),
            "target_version": target_version,
        }
        if context_extra is not None:
            context.update(context_extra)

        await self._notifications.send(
            template=NotificationTemplate.RESUBMIT_REQUESTED,
            recipient_user_id=recipient_user_id,
            recipient_email=recipient_email,
            context=context,
            related=("resubmit_request", rr.id),
        )

        # CR-006: audit after commit, before return. The notification
        # service already committed its own audit row inside send(); here
        # we record the resubmit-specific event separately.
        await self._audit.record(
            action=AuditAction.RESUBMIT_REQUEST,
            resource_type="resubmit_request",
            resource_id=rr.id,
            user_id=requester_user_id,
            details={
                "cycle_id": str(cycle_id),
                "org_unit_id": str(org_unit_id),
                "target_version": target_version,
            },
        )
        await self._db.commit()
        return rr

    async def list(
        self,
        cycle_id: UUID,
        org_unit_id: UUID,
    ) -> list[ResubmitRequest]:
        """List resubmit requests for a (cycle, org unit) pair.

        Args:
            cycle_id: Target cycle UUID.
            org_unit_id: Target org unit UUID.

        Returns:
            list[ResubmitRequest]: Rows ordered by ``requested_at`` desc.
        """
        return await self._repo.list_resubmits(cycle_id, org_unit_id)
