"""Template-file coverage tests for :mod:`app.domain.notifications.templates`.

These tests assert two things:

1. Every member of :class:`NotificationTemplate` has a matching
   ``<value>.txt`` file under :data:`TEMPLATES_DIR` (CR-003 coverage).
2. Each template renders to a non-empty subject and body when fed a
   complete context dict. Rendering goes through :class:`EmailClient`'s
   real Jinja2 environment so the ``Subject:`` convention is exercised
   end-to-end.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.domain.notifications.templates import TEMPLATES_DIR, NotificationTemplate
from app.infra.email import EmailClient


def test_every_enum_member_has_a_template_file() -> None:
    """Assert every enum value maps to an existing ``.txt`` file."""
    for member in NotificationTemplate:
        path = TEMPLATES_DIR / f"{member.value}.txt"
        assert path.exists(), f"Missing template file for {member.value}"
        assert path.stat().st_size > 0, f"Template file for {member.value} is empty"


# Reason: every enum member gets a complete context dict so Jinja2's
# ``StrictUndefined`` never fires during rendering.
_RENDER_CONTEXTS: dict[NotificationTemplate, dict[str, Any]] = {
    NotificationTemplate.CYCLE_OPENED: {
        "cycle_fiscal_year": 2026,
        "deadline": "2026-02-28",
        "cycle_url": "https://bcms.example/cycles/2026",
    },
    NotificationTemplate.UPLOAD_CONFIRMED: {
        "org_unit_name": "Finance-HQ",
        "version": 3,
        "filename": "2026_budget_v3.xlsx",
        "uploaded_at": "2026-01-15T09:30:00+08:00",
        "upload_url": "https://bcms.example/uploads/abc",
    },
    NotificationTemplate.RESUBMIT_REQUESTED: {
        "cycle_fiscal_year": 2026,
        "org_unit_name": "Finance-HQ",
        "reason": "Row 42 has a negative amount",
        "requested_by": "alice@example",
        "template_url": "https://bcms.example/templates/abc",
    },
    NotificationTemplate.DEADLINE_REMINDER: {
        "cycle_fiscal_year": 2026,
        "deadline": "2026-02-28",
        "days_remaining": 3,
        "upload_url": "https://bcms.example/uploads/abc",
    },
    NotificationTemplate.PERSONNEL_IMPORTED: {
        "fiscal_year": 2026,
        "uploader_name": "bob@example",
        "affected_count": 42,
    },
    NotificationTemplate.SHARED_COST_IMPORTED: {
        "org_unit_name": "Finance-HQ",
        "fiscal_year": 2026,
        "diff_summary": "+3 units, -1 unit",
    },
    NotificationTemplate.REPORT_EXPORT_READY: {
        "cycle_fiscal_year": 2026,
        "file_url": "https://bcms.example/exports/abc.xlsx",
        "row_count": 42,
        "expires_at": "2026-04-13T12:00:00+00:00",
    },
}


@pytest.mark.parametrize("member", list(NotificationTemplate))
def test_template_renders_with_full_context(member: NotificationTemplate) -> None:
    """Every template renders to a non-empty subject and body."""
    client = EmailClient(template_dir=TEMPLATES_DIR)
    context = _RENDER_CONTEXTS[member]
    subject, body = client._render(str(member.value), context)
    assert subject.strip() != "", f"Empty subject for {member.value}"
    assert body.strip() != "", f"Empty body for {member.value}"
