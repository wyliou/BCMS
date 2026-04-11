# Spec: infra/email

Module: `backend/src/app/infra/email/__init__.py` (+ `_client.py`, `_renderer.py`, `fake_smtp.py` if needed for ≤500 lines)
Tests: `backend/tests/unit/infra/test_email.py`

## FRs

- FR-013 (`upload_confirmed` email)
- FR-018 (`resubmit_requested` email)
- FR-020 (`deadline_reminder` email)
- FR-026 (`personnel_imported` email)
- FR-029 (`shared_cost_imported` email)

## Exports

```python
from dataclasses import dataclass

@dataclass
class SendResult:
    """Result of an email send attempt.

    Attributes:
        success (bool): True if the email was accepted by the SMTP relay.
        message_id (str | None): SMTP message ID on success; None on failure.
        error (str | None): Error description on failure; None on success.
    """
    success: bool
    message_id: str | None
    error: str | None


class EmailClient:
    """Async email client using aiosmtplib and Jinja2 template rendering.

    Intended to be constructed once at startup and reused per request via dependency injection.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the email client with SMTP configuration from settings.

        Args:
            settings (Settings): Application settings providing SMTP host/port/credentials.
        """

    async def send(
        self,
        template: str,
        recipient_email: str,
        context: dict[str, object],
        *,
        cc: list[str] | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        """Render a Jinja2 email template and send via aiosmtplib.

        The template name maps to a file under domain/notifications/templates/<template>.txt.
        The first line of the template is the subject; remaining lines are the body.

        Args:
            template (str): Template name (e.g. 'upload_confirmed'). Must be a member of
                NotificationTemplate enum. Rendered via Jinja2.
            recipient_email (str): Recipient address (plaintext email, decrypted by caller).
            context (dict[str, object]): Variables passed to the Jinja2 template.
            cc (list[str] | None): Optional CC addresses.
            reply_to (str | None): Optional Reply-To header. Defaults to settings.smtp_reply_to.

        Returns:
            SendResult: Success or failure result with message_id.

        Raises:
            InfraError: code='NOTIFY_001' if SMTP relay is unreachable or connection times out.
        """

    async def send_batch(
        self,
        template: str,
        recipient_emails: list[str],
        context: dict[str, object],
    ) -> list[SendResult]:
        """Send the same rendered email to multiple recipients (one SMTP call per recipient).

        Args:
            template (str): Template name.
            recipient_emails (list[str]): List of recipient addresses.
            context (dict[str, object]): Shared template context for all recipients.

        Returns:
            list[SendResult]: One result per recipient, in the same order.
        """


class FakeSMTP:
    """In-memory test double for EmailClient.

    Stores sent messages in a list for assertion in tests. Simulates success or
    configurable failure.
    """

    sent: list[dict[str, object]]
    should_fail: bool

    def __init__(self, *, should_fail: bool = False) -> None:
        """Initialize FakeSMTP.

        Args:
            should_fail (bool): If True, send() raises InfraError('NOTIFY_001', ...).
        """

    async def send(
        self,
        template: str,
        recipient_email: str,
        context: dict[str, object],
        *,
        cc: list[str] | None = None,
        reply_to: str | None = None,
    ) -> SendResult:
        """Simulate send; append to self.sent or raise if should_fail=True.

        Args:
            template (str): Template name.
            recipient_email (str): Recipient address.
            context (dict[str, object]): Template context.
            cc (list[str] | None): CC addresses.
            reply_to (str | None): Reply-To.

        Returns:
            SendResult: Success result with fake message_id.

        Raises:
            InfraError: code='NOTIFY_001' if should_fail is True.
        """

    async def send_batch(
        self,
        template: str,
        recipient_emails: list[str],
        context: dict[str, object],
    ) -> list[SendResult]:
        """Simulate batch send; calls self.send per recipient.

        Args:
            template (str): Template name.
            recipient_emails (list[str]): Recipient addresses.
            context (dict[str, object]): Template context.

        Returns:
            list[SendResult]: Results per recipient.
        """
```

## Imports

| Module | Symbols |
|---|---|
| `aiosmtplib` | `SMTP`, `SMTPException` |
| `email.mime.text` | `MIMEText` |
| `email.mime.multipart` | `MIMEMultipart` |
| `jinja2` | `Environment`, `FileSystemLoader`, `TemplateNotFound` |
| `pathlib` | `Path` |
| `app.config` | `Settings`, `get_settings` |
| `app.core.errors` | `InfraError` |
| `structlog` | `get_logger` |

## Template Resolution

Templates live in `backend/src/app/domain/notifications/templates/`. `EmailClient` receives the template directory path at construction (or derives it from the package path). Template file name: `{template}.txt`. First line = subject, remainder = body. Jinja2 `Environment` is configured with `autoescape=False` (plain text email).

## Side Effects

- Opens SMTP connection per `send()` call (or reuses a connection with context manager — `aiosmtplib` supports async with SMTP).
- Logs `email.sent` at INFO, `email.failed` at WARN.

## Gotchas

- `aiosmtplib` uses `async with SMTP(...)` context manager per send to avoid connection leaks.
- SMTP connection errors must be caught as `aiosmtplib.SMTPException` and wrapped into `InfraError("NOTIFY_001", ...)`.
- `FakeSMTP` must implement the same interface as `EmailClient` so tests can inject it as a direct substitute without mocking.
- Template rendering errors (missing variable) should raise `InfraError("SYS_003", ...)` — they are a programmer error, not a user error.
- The `recipient_email` passed here is the plaintext email (domain code decrypts before calling). This module never handles encrypted data.

## Consistency Constraints

- **CR-001 Stage B check:** *"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
  - SMTP failures raise `InfraError("NOTIFY_001", ...)`.

## Tests

1. `test_fake_smtp_records_sent_messages` — `FakeSMTP.send(...)` appends to `sent`.
2. `test_fake_smtp_raises_on_should_fail` — `should_fail=True`; `send` raises `InfraError("NOTIFY_001", ...)`.
3. `test_email_client_send_calls_smtp` — patch `aiosmtplib.SMTP` with a mock; assert `send_message` called.
4. `test_email_client_smtp_error_raises_notify_001` — patch SMTP to raise `SMTPException`; assert `InfraError("NOTIFY_001", ...)`.
5. `test_render_uses_jinja_context` — `FakeSMTP` records the rendered body; assert context variable appears in stored message.
6. `test_send_batch_returns_one_result_per_recipient` — three recipients; `send_batch` returns list of length 3.
