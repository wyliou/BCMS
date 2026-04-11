"""Unit tests for :mod:`app.domain.cycles.reminders`."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.domain.cycles.models import CycleState
from app.domain.cycles.reminders import DispatchSummary, set_reminder_schedule
from app.domain.notifications.templates import NotificationTemplate
from tests.unit.cycles.conftest import FakeSession, make_cycle


# ------------------------------------------------------------ set_reminder_schedule
async def test_set_reminder_schedule_replaces_rows(fake_session: FakeSession) -> None:
    """Passing a new list drops any existing rows and inserts the new ones."""
    cycle_id = uuid4()
    inserted = await set_reminder_schedule(fake_session, cycle_id, [7, 3, 1])  # type: ignore[arg-type]
    assert len(inserted) == 3
    assert {r.days_before for r in fake_session.reminders} == {7, 3, 1}

    # Replace with a shorter schedule.
    await set_reminder_schedule(fake_session, cycle_id, [1])  # type: ignore[arg-type]
    remaining = [r for r in fake_session.reminders if r.cycle_id == cycle_id]
    assert len(remaining) == 1
    assert remaining[0].days_before == 1


async def test_set_reminder_schedule_empty_disables(fake_session: FakeSession) -> None:
    """An empty list leaves zero rows for the cycle."""
    cycle_id = uuid4()
    await set_reminder_schedule(fake_session, cycle_id, [7])  # type: ignore[arg-type]
    await set_reminder_schedule(fake_session, cycle_id, [])  # type: ignore[arg-type]
    assert [r for r in fake_session.reminders if r.cycle_id == cycle_id] == []


async def test_set_reminder_schedule_rejects_non_positive(fake_session: FakeSession) -> None:
    """Zero / negative entries raise :class:`ValueError`."""
    with pytest.raises(ValueError):
        await set_reminder_schedule(fake_session, uuid4(), [0])  # type: ignore[arg-type]


# ---------------------------------------------------------- dispatch_deadline_reminders
class _FakeNotifications:
    """Minimal stand-in for :class:`NotificationService`."""

    def __init__(self) -> None:
        """Initialize an empty send log."""
        self.sent: list[dict[str, Any]] = []

    async def send(
        self,
        *,
        template: NotificationTemplate,
        recipient_user_id: UUID,
        recipient_email: str,
        context: dict[str, Any],
        related: tuple[str, UUID] | None = None,
    ) -> Any:
        """Record the call and return a "sent" stand-in."""
        self.sent.append(
            {
                "template": template,
                "recipient_user_id": recipient_user_id,
                "recipient_email": recipient_email,
                "context": context,
                "related": related,
            }
        )

        class _Result:
            status = "sent"

        return _Result()


async def test_dispatch_no_open_cycles(
    fake_session: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When there are no Open cycles the summary reports zero work."""
    from app.domain.cycles import reminders as reminders_mod

    async def _fake_unsubmitted(db: Any, cycle_id: UUID) -> list[UUID]:
        return []

    monkeypatch.setattr(reminders_mod, "unsubmitted_for_cycle", _fake_unsubmitted)

    summary = await reminders_mod.dispatch_deadline_reminders(
        fake_session,  # type: ignore[arg-type]
        _FakeNotifications(),  # type: ignore[arg-type]
        today=date(2026, 12, 30),
    )
    assert summary == DispatchSummary(cycle_count=0, notifications_sent=0, notifications_failed=0)


async def test_dispatch_skips_when_days_before_not_matched(
    fake_session: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Open cycles whose remaining days don't match any schedule are skipped."""
    from app.domain.cycles import reminders as reminders_mod

    cycle = make_cycle(
        status=CycleState.open,
        deadline=date(2026, 12, 31),
    )
    fake_session.cycles.append(cycle)
    await set_reminder_schedule(fake_session, cycle.id, [7])  # type: ignore[arg-type]

    async def _fake_unsubmitted(db: Any, cycle_id: UUID) -> list[UUID]:
        return [uuid4()]

    monkeypatch.setattr(reminders_mod, "unsubmitted_for_cycle", _fake_unsubmitted)

    notifications = _FakeNotifications()
    summary = await reminders_mod.dispatch_deadline_reminders(
        fake_session,  # type: ignore[arg-type]
        notifications,  # type: ignore[arg-type]
        today=cycle.deadline - timedelta(days=3),  # 3 days remaining, schedule has 7
    )
    assert summary.notifications_sent == 0
    assert notifications.sent == []


async def test_dispatch_sends_when_days_before_matches(
    fake_session: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When days_before matches, every unsubmitted manager receives a reminder."""
    from app.core.security.roles import Role
    from app.domain.cycles import reminders as reminders_mod
    from tests.unit.cycles.conftest import make_org_unit, make_user

    cycle = make_cycle(
        status=CycleState.open,
        deadline=date(2026, 12, 31),
    )
    fake_session.cycles.append(cycle)
    await set_reminder_schedule(fake_session, cycle.id, [3])  # type: ignore[arg-type]

    unit = make_org_unit(code="4000")
    fake_session.org_units = [unit]
    manager = make_user(
        roles=[Role.FilingUnitManager],
        org_unit_id=unit.id,
        email="mgr@example.invalid",
    )
    fake_session.users = [manager]

    async def _fake_unsubmitted(db: Any, cycle_id: UUID) -> list[UUID]:
        return [unit.id]

    monkeypatch.setattr(reminders_mod, "unsubmitted_for_cycle", _fake_unsubmitted)

    notifications = _FakeNotifications()
    summary = await reminders_mod.dispatch_deadline_reminders(
        fake_session,  # type: ignore[arg-type]
        notifications,  # type: ignore[arg-type]
        today=cycle.deadline - timedelta(days=3),  # exactly 3 remaining
    )
    assert summary.notifications_sent == 1
    assert len(notifications.sent) == 1
    call = notifications.sent[0]
    assert call["template"] is NotificationTemplate.DEADLINE_REMINDER
    assert call["recipient_email"] == "mgr@example.invalid"
    assert call["context"]["days_before"] == 3
