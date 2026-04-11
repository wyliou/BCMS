"""Unit tests for :mod:`app.infra.email`."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import InfraError
from app.infra.email import EmailClient, FakeSMTP, SendResult


async def test_fake_smtp_records_send() -> None:
    """FakeSMTP stores every message for later inspection."""
    fake = FakeSMTP()
    result = await fake.send("cycle_opened", "alice@example.invalid", {"name": "Alice"})
    assert isinstance(result, SendResult)
    assert result.success is True
    assert len(fake.sent) == 1
    message = fake.sent[0]
    assert message.template == "cycle_opened"
    assert message.recipient == "alice@example.invalid"
    assert message.context == {"name": "Alice"}


async def test_fake_smtp_failure_mode() -> None:
    """``should_fail=True`` raises ``NOTIFY_001``."""
    fake = FakeSMTP(should_fail=True)
    with pytest.raises(InfraError) as excinfo:
        await fake.send("cycle_opened", "alice@example.invalid", {})
    assert excinfo.value.code == "NOTIFY_001"


async def test_fake_smtp_preserves_cc_list() -> None:
    """CC list is copied into the stored message."""
    fake = FakeSMTP()
    await fake.send(
        "deadline_reminder",
        "manager@example.invalid",
        {},
        cc=["reviewer@example.invalid"],
    )
    assert fake.sent[0].cc == ["reviewer@example.invalid"]


def test_email_client_missing_template_fallback(tmp_path: Path) -> None:
    """Missing templates fall back to a context-dump body."""
    client = EmailClient(template_dir=tmp_path)
    subject, body = client._render("unknown", {"k": "v"})
    assert "unknown" in subject
    assert "'k': 'v'" in body


def test_email_client_renders_template(tmp_path: Path) -> None:
    """A simple ``.txt`` template is rendered with Jinja variables."""
    (tmp_path / "welcome.txt").write_text(
        "[BCMS] Welcome {{ name }}\n\nBody text for {{ name }}\n",
        encoding="utf-8",
    )
    client = EmailClient(template_dir=tmp_path)
    subject, body = client._render("welcome", {"name": "Alice"})
    assert subject == "[BCMS] Welcome Alice"
    assert "Body text for Alice" in body


async def test_email_client_send_raises_on_transport_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transport error is wrapped as ``NOTIFY_001``."""
    client = EmailClient(template_dir=tmp_path)

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("relay unreachable")

    monkeypatch.setattr("app.infra.email.aiosmtplib.send", _boom)
    with pytest.raises(InfraError) as excinfo:
        await client.send("welcome", "alice@example.invalid", {"name": "Alice"})
    assert excinfo.value.code == "NOTIFY_001"
