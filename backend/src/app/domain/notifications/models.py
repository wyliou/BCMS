"""SQLAlchemy ORM models for the ``notifications`` and ``resubmit_requests`` tables.

Both models mirror the Alembic baseline DDL in
``alembic/versions/0001_baseline.py`` exactly. Column choices are portable
across production PostgreSQL and the in-memory SQLite engine used by unit
tests — dialect-specific types (``postgresql.UUID``, ``JSONB``) are wrapped
in :class:`GUID` / :class:`JSONDict` decorators reused from
``app.domain.audit.models``.

The ORM deliberately stays thin — all business rules (resubmit sequencing,
SMTP failure tolerance, audit recording) live in
:class:`app.domain.notifications.service.NotificationService` and
:class:`app.domain.notifications.resubmit.ResubmitRequestService`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now_utc
from app.domain.audit.models import GUID
from app.infra.db.base import Base

__all__ = ["Notification", "ResubmitRequest"]


class Notification(Base):
    """SQLAlchemy ORM for the ``notifications`` table.

    Rows are written exclusively via
    :class:`app.domain.notifications.service.NotificationService.send` (and
    the batch / resend helpers). Status transitions through
    ``queued -> sent`` on success or ``queued -> failed`` on SMTP failure;
    ``bounced`` is reserved for future async bounce handling and never set
    synchronously by the service.

    The ``type`` column uses the shared Postgres ``notification_type`` enum
    created in the baseline migration; this model stores the value as a
    plain string so SQLite unit tests do not need the enum type installed.
    """

    __tablename__ = "notifications"

    id: Mapped[UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid4,
    )
    recipient_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="email",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="queued",
    )
    related_resource_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    related_resource_id: Mapped[UUID | None] = mapped_column(
        GUID(),
        nullable=True,
    )
    link_url: Mapped[str | None] = mapped_column(
        Text(),
        nullable=True,
    )
    subject: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    body_excerpt: Mapped[str | None] = mapped_column(
        Text(),
        nullable=True,
    )
    bounce_reason: Mapped[str | None] = mapped_column(
        Text(),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class ResubmitRequest(Base):
    """SQLAlchemy ORM for the ``resubmit_requests`` table.

    One row is inserted per
    :meth:`app.domain.notifications.resubmit.ResubmitRequestService.create`
    call. Per **CR-007** (FR-019), the row is written and committed before
    the notification email is attempted — the commit must happen even if
    email later fails so the request stays auditable.
    """

    __tablename__ = "resubmit_requests"

    id: Mapped[UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid4,
    )
    cycle_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("budget_cycles.id"),
        nullable=False,
    )
    org_unit_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("org_units.id"),
        nullable=False,
    )
    requester_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )
    target_version: Mapped[int | None] = mapped_column(
        Integer(),
        nullable=True,
    )
    reason: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
    )
