"""Async email adapter — aiosmtplib + Jinja2 + in-memory ``FakeSMTP`` test double.

Templates live in ``app/domain/notifications/templates/`` and are loaded lazily
by :class:`EmailClient` on first render. The first line of a template file is
treated as the ``Subject:`` header; everything after the first blank line is
the body. Batch 2 ships the actual templates — until then :class:`EmailClient`
falls back to rendering ``context`` as the body directly so tests that do not
depend on real templates still exercise the send path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import aiosmtplib
import jinja2
import structlog

from app.config import Settings, get_settings
from app.core.errors import InfraError

__all__ = ["SendResult", "EmailClient", "FakeSMTP"]


_LOG = structlog.get_logger(__name__)


@dataclass
class SendResult:
    """Outcome of an email send attempt.

    Attributes:
        success: ``True`` iff the relay accepted the message.
        message_id: SMTP message id (or a fake id for :class:`FakeSMTP`).
        error: Short description when ``success`` is ``False``.
    """

    success: bool
    message_id: str | None = None
    error: str | None = None


def _default_template_dir() -> Path:
    """Return the default Jinja template directory.

    The directory may not exist during Batch 0 — :class:`EmailClient` handles
    missing templates gracefully by falling back to a context dump.

    Returns:
        Path: ``app/domain/notifications/templates`` as an absolute path.
    """
    # Reason: compute relative to this file so tests can drop replacement
    # templates under ``tmp_path`` without relying on cwd.
    return Path(__file__).resolve().parents[2] / "domain" / "notifications" / "templates"


class EmailClient:
    """Async email client backed by :mod:`aiosmtplib` and Jinja2 templates.

    Constructed once per process (from FastAPI dependency wiring). The SMTP
    connection is opened per ``send`` call — the intranet relay is expected to
    be nearby so the handshake cost is acceptable and this keeps the client
    stateless.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        template_dir: Path | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            settings: Application settings. Defaults to :func:`get_settings`.
            template_dir: Directory to load Jinja templates from. Defaults to
                ``app/domain/notifications/templates``.
        """
        self._settings = settings or get_settings()
        self._template_dir = template_dir or _default_template_dir()
        if self._template_dir.exists():
            loader: jinja2.BaseLoader = jinja2.FileSystemLoader(str(self._template_dir))
        else:
            loader = jinja2.DictLoader({})
        self._env = jinja2.Environment(
            loader=loader,
            autoescape=False,
            undefined=jinja2.StrictUndefined,
        )

    def _render(self, template: str, context: dict[str, Any]) -> tuple[str, str]:
        """Render a template to ``(subject, body)``.

        Falls back to a generic subject + ``repr(context)`` body when the
        requested template file is not present — this keeps Batch 0 email
        tests useful while Batch 2 ships the real templates.

        Args:
            template: Template name (without extension).
            context: Variables to inject.

        Returns:
            tuple[str, str]: ``(subject, body)``.
        """
        try:
            tpl = self._env.get_template(f"{template}.txt")
        except jinja2.TemplateNotFound:
            return (f"[BCMS] {template}", f"context={context!r}")
        rendered = tpl.render(**context)
        lines = rendered.splitlines()
        if not lines:
            return (f"[BCMS] {template}", "")
        subject = lines[0].strip()
        # Reason: allow the author to separate subject and body with an empty
        # line; fall back to "everything after line 0" otherwise.
        if len(lines) > 1 and lines[1] == "":
            body = "\n".join(lines[2:])
        else:
            body = "\n".join(lines[1:])
        return (subject, body)

    async def send(
        self,
        template: str,
        recipient: str,
        context: dict[str, Any],
        *,
        cc: list[str] | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        """Render a template and send it via the configured SMTP relay.

        Args:
            template: Template name (without ``.txt`` extension).
            recipient: Recipient email address (plaintext).
            context: Variables to render in the template.
            cc: Optional CC recipients.
            reply_to: Optional ``Reply-To`` override.

        Returns:
            SendResult: Success or failure record.

        Raises:
            InfraError: ``NOTIFY_001`` when the SMTP relay is unreachable or
                refuses the message.
        """
        subject, body = self._render(template, context)
        message = EmailMessage()
        message["From"] = self._settings.email_from
        message["To"] = recipient
        if cc:
            message["Cc"] = ", ".join(cc)
        resolved_reply_to = reply_to or self._settings.smtp_reply_to
        if resolved_reply_to:
            message["Reply-To"] = resolved_reply_to
        message["Subject"] = subject
        message.set_content(body)

        try:
            await aiosmtplib.send(
                message,
                hostname=self._settings.smtp_host or "localhost",
                port=self._settings.smtp_port,
                username=self._settings.smtp_user,
                password=self._settings.smtp_password,
                use_tls=False,
                start_tls=self._settings.smtp_use_tls,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            _LOG.warning(
                "email.send_failed",
                template=template,
                recipient=recipient,
                error=str(exc),
            )
            raise InfraError("NOTIFY_001", f"SMTP send failed: {exc}") from exc
        _LOG.info("email.sent", template=template, recipient=recipient)
        return SendResult(success=True, message_id=message.get("Message-ID"))


@dataclass
class _FakeSentMessage:
    """Record of a message captured by :class:`FakeSMTP`."""

    template: str
    recipient: str
    context: dict[str, Any]
    cc: list[str] | None
    reply_to: str | None


@dataclass
class FakeSMTP:
    """In-memory :class:`EmailClient` substitute for tests.

    Captures every message passed to :meth:`send` in :attr:`sent`. When
    :attr:`should_fail` is ``True``, :meth:`send` raises :class:`InfraError`
    with code ``NOTIFY_001`` to simulate an unreachable relay.

    Attributes:
        sent: List of captured messages.
        should_fail: When ``True``, :meth:`send` raises instead of recording.
    """

    sent: list[_FakeSentMessage] = field(default_factory=list)
    should_fail: bool = False

    async def send(
        self,
        template: str,
        recipient: str,
        context: dict[str, Any],
        *,
        cc: list[str] | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        """Record or fail a send attempt.

        Args:
            template: Template name.
            recipient: Recipient address.
            context: Template variables (stored as-is).
            cc: Optional CC recipients.
            reply_to: Optional Reply-To override.

        Returns:
            SendResult: Success record with a fake message id.

        Raises:
            InfraError: ``NOTIFY_001`` when :attr:`should_fail` is ``True``.
        """
        if self.should_fail:
            raise InfraError("NOTIFY_001", "FakeSMTP configured to fail")
        self.sent.append(
            _FakeSentMessage(
                template=template,
                recipient=recipient,
                context=dict(context),
                cc=list(cc) if cc else None,
                reply_to=reply_to,
            )
        )
        return SendResult(success=True, message_id=f"fake-{len(self.sent)}")
