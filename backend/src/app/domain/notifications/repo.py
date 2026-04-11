"""Repository (data-access layer) for notifications + resubmit_requests.

This module owns reads + low-level inserts for
:class:`app.domain.notifications.models.Notification` and
:class:`app.domain.notifications.models.ResubmitRequest`. All business rules
— template rendering, SMTP dispatch, CR-007 sequencing, audit recording —
live in the service layer.

The repository never commits on the caller's behalf. Transaction
boundaries belong to the service / API layer.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notifications.models import Notification, ResubmitRequest

__all__ = ["NotificationRepo"]


class NotificationRepo:
    """Data-access layer for notifications and resubmit requests.

    The repository is a thin wrapper around the async session — it adds
    ORM instances, flushes to assign server defaults, and runs a handful of
    read queries used by the service and API layers. It does not commit.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an active async session.

        Args:
            db: Active async session managed by the caller.
        """
        self._db = db

    # ------------------------------------------------------------ notifications
    async def insert(self, notif: Notification) -> Notification:
        """Add a new :class:`Notification` to the session and flush.

        Flushing forces server defaults (``id``, ``created_at``) to be
        assigned before the row is returned. Does NOT commit — the caller
        owns transaction boundaries.

        Args:
            notif: Fully populated notification row.

        Returns:
            Notification: The same ORM instance, with defaults populated.
        """
        self._db.add(notif)
        await self._db.flush()
        return notif

    async def get(self, notif_id: UUID) -> Notification | None:
        """Return the notification row with the given id, or ``None``.

        Args:
            notif_id: Notification UUID.

        Returns:
            Notification | None: The row, or ``None`` when not found.
        """
        stmt = select(Notification).where(Notification.id == notif_id)
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def mark_sent(self, notif_id: UUID, sent_at: datetime) -> None:
        """Update a notification to ``status=sent`` and stamp ``sent_at``.

        Args:
            notif_id: Notification UUID.
            sent_at: UTC timestamp to record as the send time.
        """
        notif = await self.get(notif_id)
        if notif is None:
            return
        notif.status = "sent"
        notif.sent_at = sent_at
        notif.bounce_reason = None
        await self._db.flush()

    async def mark_failed(self, notif_id: UUID, error: str) -> None:
        """Update a notification to ``status=failed`` and record the error.

        Args:
            notif_id: Notification UUID.
            error: Short description of the failure (stored in
                ``bounce_reason``).
        """
        notif = await self.get(notif_id)
        if notif is None:
            return
        notif.status = "failed"
        notif.bounce_reason = error
        await self._db.flush()

    async def list_failed(self, limit: int = 100) -> list[Notification]:
        """Return failed notification rows ordered by ``created_at`` desc.

        Args:
            limit: Maximum number of rows to return.

        Returns:
            list[Notification]: Failed rows, newest first.
        """
        stmt = (
            select(Notification)
            .where(Notification.status == "failed")
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # ---------------------------------------------------------- resubmit_requests
    async def insert_resubmit(self, rr: ResubmitRequest) -> ResubmitRequest:
        """Add a new :class:`ResubmitRequest` to the session and flush.

        Args:
            rr: Fully populated resubmit request row.

        Returns:
            ResubmitRequest: The same ORM instance with defaults populated.
        """
        self._db.add(rr)
        await self._db.flush()
        return rr

    async def list_resubmits(
        self,
        cycle_id: UUID,
        org_unit_id: UUID,
    ) -> list[ResubmitRequest]:
        """Return all resubmit requests for a (cycle, org unit) pair.

        Args:
            cycle_id: Target cycle UUID.
            org_unit_id: Target org unit UUID.

        Returns:
            list[ResubmitRequest]: Matching rows ordered by ``requested_at`` desc.
        """
        stmt = (
            select(ResubmitRequest)
            .where(
                and_(
                    ResubmitRequest.cycle_id == cycle_id,
                    ResubmitRequest.org_unit_id == org_unit_id,
                )
            )
            .order_by(ResubmitRequest.requested_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
