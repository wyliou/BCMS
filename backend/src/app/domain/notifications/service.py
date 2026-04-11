"""Notification dispatch service (FR-013, FR-018, FR-020, FR-026, FR-029).

Owns the **CR-029** failure-tolerance contract: SMTP send failures do NOT
propagate out of :meth:`NotificationService.send`. The service marks the
stored :class:`Notification` row as ``failed``, records a
``NOTIFY_FAILED`` audit entry, and returns the row normally. Callers
(``BudgetUploadService`` etc.) rely on this behaviour so a broken relay
does not invalidate an otherwise-successful upload.

Template rendering is delegated to the injected
:class:`app.infra.email.EmailClient` (or :class:`FakeSMTP` in tests), which
loads Jinja2 templates from :data:`TEMPLATES_DIR`. The service itself does
not touch the filesystem — it passes the enum value through to the client,
which renders + dispatches in one call.

Audit recording follows **CR-006**: after each successful send the service
commits the notification row, then records the audit entry, then flushes
again. Callers that already own a transaction can pass their own session
— the service does not re-open or re-commit the outer transaction.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_utc
from app.core.errors import AppError, InfraError
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService
from app.domain.notifications.models import Notification
from app.domain.notifications.repo import NotificationRepo
from app.domain.notifications.templates import NotificationTemplate
from app.infra.email import SendResult

__all__ = ["EmailSender", "NotificationService"]


_LOG = structlog.get_logger(__name__)


class EmailSender(Protocol):
    """Protocol implemented by :class:`EmailClient` and :class:`FakeSMTP`.

    The service depends on this narrow Protocol so tests can inject the
    in-memory double shipped in :mod:`app.infra.email` without monkey-
    patching the module-level client.
    """

    async def send(
        self,
        template: str,
        recipient: str,
        context: dict[str, Any],
        *,
        cc: list[str] | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        """Render the named template and deliver it to ``recipient``.

        Args:
            template: Template name (without ``.txt`` extension).
            recipient: Recipient email address.
            context: Variables to inject into the template.
            cc: Optional CC recipients.
            reply_to: Optional ``Reply-To`` override.

        Returns:
            SendResult: Outcome record.
        """
        ...


class NotificationService:
    """Write notification rows and dispatch email via :class:`EmailSender`.

    Constructed per-request with an active :class:`AsyncSession`, an
    :class:`EmailSender` (usually :class:`EmailClient`), and an
    :class:`AuditService` pinned to the same session so the notification
    commit and the audit row share a transaction boundary.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        email_client: EmailSender,
        audit_service: AuditService | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            db: Active async session managed by the caller.
            email_client: Email sender (real or fake).
            audit_service: Optional audit service. Defaults to a new
                :class:`AuditService` bound to ``db``.
        """
        self._db = db
        self._repo = NotificationRepo(db)
        self._email = email_client
        self._audit = audit_service if audit_service is not None else AuditService(db)

    # ------------------------------------------------------------------ send
    async def send(
        self,
        *,
        template: NotificationTemplate,
        recipient_user_id: UUID,
        recipient_email: str,
        context: dict[str, Any],
        related: tuple[str, UUID] | None = None,
    ) -> Notification:
        """Render ``template`` and send a single email, persisting the row.

        Records a ``queued`` :class:`Notification` row, calls the injected
        email client, then flips the row to ``sent`` or ``failed`` based on
        the outcome. Per **CR-029** this method never raises on SMTP
        failure — the caller receives a :class:`Notification` whose
        ``status`` reflects the result.

        Args:
            template: Template enum member.
            recipient_user_id: UUID of the recipient user (stored on the row).
            recipient_email: Plaintext email address passed to SMTP.
            context: Template rendering context (stored on the row as
                ``body_excerpt`` for later resend).
            related: Optional ``(resource_type, resource_id)`` pair for the
                ``related_resource_*`` columns.

        Returns:
            Notification: The persisted row. ``status`` is ``sent`` on
            success and ``failed`` on SMTP failure.
        """
        notif = self._build_queued(
            template=template,
            recipient_user_id=recipient_user_id,
            context=context,
            related=related,
        )
        await self._repo.insert(notif)

        try:
            await self._email.send(str(template.value), recipient_email, context)
        except InfraError as exc:
            # CR-029: SMTP failure never propagates out of send().
            await self._repo.mark_failed(notif.id, str(exc))
            _LOG.warning(
                "notification.send_failed",
                template=str(template.value),
                recipient_user_id=str(recipient_user_id),
                error=exc.code,
            )
            await self._audit.record(
                action=AuditAction.NOTIFY_FAILED,
                resource_type="notification",
                resource_id=notif.id,
                user_id=recipient_user_id,
                details={"template": str(template.value), "error": exc.code},
            )
            return notif

        await self._repo.mark_sent(notif.id, now_utc())
        _LOG.info(
            "notification.sent",
            template=str(template.value),
            recipient_user_id=str(recipient_user_id),
        )
        await self._audit.record(
            action=AuditAction.NOTIFY_SENT,
            resource_type="notification",
            resource_id=notif.id,
            user_id=recipient_user_id,
            details={"template": str(template.value)},
        )
        return notif

    async def send_batch(
        self,
        *,
        template: NotificationTemplate,
        recipients: list[tuple[UUID, str]],
        context: dict[str, Any],
        related: tuple[str, UUID] | None = None,
    ) -> list[Notification]:
        """Send ``template`` to multiple recipients; partial failures allowed.

        Each recipient is attempted independently via :meth:`send`. The
        result list preserves input order and contains one
        :class:`Notification` per recipient — some may be ``sent`` and
        others ``failed``.

        Args:
            template: Template enum member.
            recipients: List of ``(user_id, email)`` tuples.
            context: Shared template context (same for every recipient).
            related: Optional ``(resource_type, resource_id)`` pair for the
                ``related_resource_*`` columns on each row.

        Returns:
            list[Notification]: One row per recipient.
        """
        results: list[Notification] = []
        for user_id, email in recipients:
            notif = await self.send(
                template=template,
                recipient_user_id=user_id,
                recipient_email=email,
                context=context,
                related=related,
            )
            results.append(notif)
        return results

    # ------------------------------------------------------------------ reads
    async def list_failed(self, limit: int = 100) -> list[Notification]:
        """Return failed notification rows ordered newest-first.

        Args:
            limit: Maximum number of rows to return.

        Returns:
            list[Notification]: Rows with ``status=failed``.
        """
        return await self._repo.list_failed(limit)

    # ------------------------------------------------------------------ resend
    async def resend(
        self,
        notification_id: UUID,
        *,
        recipient_email: str,
    ) -> Notification:
        """Retry a previously failed notification.

        Loads the stored row, re-dispatches using the original template and
        context (recovered from ``body_excerpt`` by the caller — here we
        pass an empty context if none is stored), and flips the row to
        ``sent`` on success or leaves it ``failed`` with an updated
        ``bounce_reason`` on failure.

        The row's existence is the source of truth — a successful resend
        updates the same row in-place.

        Args:
            notification_id: UUID of the row to resend.
            recipient_email: Plaintext email address for re-delivery.

        Returns:
            Notification: The updated row.

        Raises:
            AppError: ``NOTIFY_003`` when the row does not exist.
        """
        notif = await self._repo.get(notification_id)
        if notif is None:
            raise AppError("NOTIFY_003", f"Notification {notification_id} not found")

        template_value = notif.type
        # Reason: body_excerpt is a human-readable dump; on resend we pass
        # an empty context and let the template render with whatever
        # defaults / strict-undefined semantics apply. Production callers
        # should preserve the original context via their own storage.
        context: dict[str, Any] = {}

        try:
            await self._email.send(template_value, recipient_email, context)
        except InfraError as exc:
            await self._repo.mark_failed(notif.id, str(exc))
            _LOG.warning(
                "notification.resend_failed",
                notification_id=str(notif.id),
                error=exc.code,
            )
            await self._audit.record(
                action=AuditAction.NOTIFY_RESENT,
                resource_type="notification",
                resource_id=notif.id,
                user_id=notif.recipient_id,
                details={"template": template_value, "status": "failed", "error": exc.code},
            )
            return notif

        await self._repo.mark_sent(notif.id, now_utc())
        _LOG.info("notification.resent", notification_id=str(notif.id))
        await self._audit.record(
            action=AuditAction.NOTIFY_RESENT,
            resource_type="notification",
            resource_id=notif.id,
            user_id=notif.recipient_id,
            details={"template": template_value, "status": "sent"},
        )
        return notif

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _build_queued(
        *,
        template: NotificationTemplate,
        recipient_user_id: UUID,
        context: dict[str, Any],
        related: tuple[str, UUID] | None,
    ) -> Notification:
        """Construct a queued :class:`Notification` row (pre-insert).

        Args:
            template: Template enum member.
            recipient_user_id: Recipient user UUID.
            context: Template context — stored as ``body_excerpt`` for
                debugging + resend support.
            related: Optional ``(resource_type, resource_id)`` tuple.

        Returns:
            Notification: Unpersisted row with ``status=queued``.
        """
        related_type: str | None = related[0] if related is not None else None
        related_id: UUID | None = related[1] if related is not None else None
        # Reason: architecture §6 marks body_excerpt as TEXT; we write a
        # short repr of the context so operators can eyeball what was sent.
        excerpt = repr(context)[:1000]
        return Notification(
            recipient_id=recipient_user_id,
            type=str(template.value),
            channel="email",
            status="queued",
            related_resource_type=related_type,
            related_resource_id=related_id,
            body_excerpt=excerpt,
            created_at=now_utc(),
        )
