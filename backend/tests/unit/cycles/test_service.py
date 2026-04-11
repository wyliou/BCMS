"""Unit tests for :class:`app.domain.cycles.service.CycleService`."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.security.roles import Role
from app.domain.audit.actions import AuditAction
from app.domain.cycles.models import CycleState
from tests.unit.cycles.conftest import (
    FakeSession,
    make_cycle,
    make_org_unit,
    make_user,
)


# ---------------------------------------------------------------------- create
async def test_create_cycle_success(
    cycle_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """A valid call inserts a draft row and audits CYCLE_CREATE."""
    cycle = await cycle_service.create(
        fiscal_year=2026,
        deadline=date(2026, 12, 31),
        reporting_currency="TWD",
        user=system_admin,
    )
    assert cycle.status == CycleState.draft.value
    assert cycle.reporting_currency == "TWD"
    assert len(fake_session.cycles) == 1
    events = cycle_service._audit.events
    assert events[0]["action"] is AuditAction.CYCLE_CREATE


async def test_create_cycle_duplicate_raises_cycle_001(
    cycle_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """A second non-closed cycle for the same year raises ``CYCLE_001``."""
    fake_session.cycles.append(make_cycle(status=CycleState.open))

    with pytest.raises(ConflictError) as exc_info:
        await cycle_service.create(
            fiscal_year=2026,
            deadline=date(2026, 12, 31),
            reporting_currency="TWD",
            user=system_admin,
        )
    assert exc_info.value.code == "CYCLE_001"


async def test_create_cycle_allows_new_year_when_existing_is_closed(
    cycle_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """If the existing 2026 cycle is Closed, creating another is allowed."""
    fake_session.cycles.append(make_cycle(status=CycleState.closed))
    cycle = await cycle_service.create(
        fiscal_year=2026,
        deadline=date(2026, 12, 31),
        reporting_currency="TWD",
        user=system_admin,
    )
    assert cycle.status == CycleState.draft.value


async def test_create_cycle_rejects_invalid_currency(
    cycle_service: Any,
    system_admin: Any,
) -> None:
    """Non-3-letter currency payloads raise ValueError (CR-023)."""
    with pytest.raises(ValueError):
        await cycle_service.create(
            fiscal_year=2026,
            deadline=date(2026, 12, 31),
            reporting_currency="US",
            user=system_admin,
        )


# -------------------------------------------------------------------------- open
async def test_open_cycle_success(
    cycle_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """Draft → Open with all managers present returns actionable units."""
    unit_a = make_org_unit(code="4000")
    unit_b = make_org_unit(code="4010")
    fake_session.org_units = [unit_a, unit_b]
    fake_session.users = [
        make_user(roles=[Role.FilingUnitManager], org_unit_id=unit_a.id),
        make_user(roles=[Role.FilingUnitManager], org_unit_id=unit_b.id),
    ]
    cycle = make_cycle(status=CycleState.draft)
    fake_session.cycles.append(cycle)

    updated, actionable = await cycle_service.open(cycle.id, system_admin)
    assert updated.status == CycleState.open.value
    assert {u.code for u in actionable} == {"4000", "4010"}
    # Default reminder schedule [7, 3, 1] seeded.
    assert len(fake_session.reminders) == 3
    assert {r.days_before for r in fake_session.reminders} == {7, 3, 1}

    actions = [e["action"] for e in cycle_service._audit.events]
    assert AuditAction.CYCLE_OPEN in actions


async def test_open_cycle_wrong_state_raises_cycle_003(
    cycle_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """Re-opening an already-Open cycle raises ``CYCLE_003``."""
    cycle = make_cycle(status=CycleState.open)
    fake_session.cycles.append(cycle)
    with pytest.raises(ConflictError) as exc_info:
        await cycle_service.open(cycle.id, system_admin)
    assert exc_info.value.code == "CYCLE_003"


async def test_open_cycle_missing_manager_raises_cycle_002(
    cycle_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """A filing unit without a manager blocks the transition."""
    unit_a = make_org_unit(code="4000")
    unit_b = make_org_unit(code="4010")
    fake_session.org_units = [unit_a, unit_b]
    fake_session.users = [
        make_user(roles=[Role.FilingUnitManager], org_unit_id=unit_a.id),
    ]
    cycle = make_cycle(status=CycleState.draft)
    fake_session.cycles.append(cycle)

    with pytest.raises(ConflictError) as exc_info:
        await cycle_service.open(cycle.id, system_admin)
    assert exc_info.value.code == "CYCLE_002"


async def test_open_cycle_excluded_unit_bypasses_manager_check(
    cycle_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """Units explicitly excluded for the cycle do not block the open."""
    cycle = make_cycle(status=CycleState.draft)
    fake_session.cycles.append(cycle)
    excluded = make_org_unit(code="4000", excluded_for_cycle_ids=[str(cycle.id)])
    normal = make_org_unit(code="4010")
    fake_session.org_units = [excluded, normal]
    fake_session.users = [
        make_user(roles=[Role.FilingUnitManager], org_unit_id=normal.id),
    ]

    updated, actionable = await cycle_service.open(cycle.id, system_admin)
    assert updated.status == CycleState.open.value
    assert {u.code for u in actionable} == {"4010"}


# ------------------------------------------------------------------------- close
async def test_close_cycle_success(
    cycle_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """Open → Closed sets ``closed_at`` and audits CYCLE_CLOSE."""
    cycle = make_cycle(status=CycleState.open)
    fake_session.cycles.append(cycle)
    updated = await cycle_service.close(cycle.id, system_admin)
    assert updated.status == CycleState.closed.value
    assert updated.closed_at is not None
    actions = [e["action"] for e in cycle_service._audit.events]
    assert AuditAction.CYCLE_CLOSE in actions


async def test_close_wrong_state_raises_cycle_003(
    cycle_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """Closing a Draft cycle raises CYCLE_003."""
    cycle = make_cycle(status=CycleState.draft)
    fake_session.cycles.append(cycle)
    with pytest.raises(ConflictError) as exc_info:
        await cycle_service.close(cycle.id, system_admin)
    assert exc_info.value.code == "CYCLE_003"


# ------------------------------------------------------------------------ reopen
async def test_reopen_within_window_succeeds(
    cycle_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """Closed cycle inside BC_REOPEN_WINDOW_DAYS reopens successfully."""
    cycle = make_cycle(
        status=CycleState.closed,
        closed_at=datetime.now(tz=timezone.utc) - timedelta(days=1),
    )
    fake_session.cycles.append(cycle)
    updated = await cycle_service.reopen(cycle.id, "because", system_admin)
    assert updated.status == CycleState.open.value
    assert updated.reopen_reason == "because"


async def test_reopen_outside_window_raises_cycle_005(
    cycle_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """Closed longer ago than the window raises ``CYCLE_005`` (CR-037)."""
    cycle = make_cycle(
        status=CycleState.closed,
        closed_at=datetime.now(tz=timezone.utc) - timedelta(days=365),
    )
    fake_session.cycles.append(cycle)
    with pytest.raises(AppError) as exc_info:
        await cycle_service.reopen(cycle.id, "late", system_admin)
    assert exc_info.value.code == "CYCLE_005"


async def test_reopen_uses_closed_at_not_created_at(
    cycle_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """CR-037: ``closed_at`` is the reference, not ``created_at``."""
    cycle = make_cycle(
        status=CycleState.closed,
        closed_at=datetime.now(tz=timezone.utc) - timedelta(days=365),
    )
    # ``created_at`` still fresh, but ``closed_at`` is far past the window.
    cycle.created_at = datetime.now(tz=timezone.utc)
    fake_session.cycles.append(cycle)
    with pytest.raises(AppError) as exc_info:
        await cycle_service.reopen(cycle.id, "late", system_admin)
    assert exc_info.value.code == "CYCLE_005"


async def test_reopen_requires_system_admin(
    cycle_service: Any,
    fake_session: FakeSession,
) -> None:
    """Non-SystemAdmin callers are rejected with RBAC_001."""
    cycle = make_cycle(
        status=CycleState.closed,
        closed_at=datetime.now(tz=timezone.utc) - timedelta(days=1),
    )
    fake_session.cycles.append(cycle)
    fin_admin = make_user(roles=[Role.FinanceAdmin], org_unit_id=None)
    with pytest.raises(AppError) as exc_info:
        await cycle_service.reopen(cycle.id, "try", fin_admin)
    assert exc_info.value.code == "RBAC_001"


# -------------------------------------------------------------------- assert_open
async def test_assert_open_raises_cycle_004_when_closed(
    cycle_service: Any,
    fake_session: FakeSession,
) -> None:
    """``assert_open`` raises ``CYCLE_004`` when the cycle is closed."""
    cycle = make_cycle(status=CycleState.closed)
    fake_session.cycles.append(cycle)
    with pytest.raises(AppError) as exc_info:
        await cycle_service.assert_open(cycle.id)
    assert exc_info.value.code == "CYCLE_004"


async def test_assert_open_not_found_raises(
    cycle_service: Any,
) -> None:
    """``assert_open`` raises :class:`NotFoundError` for missing ids."""
    from uuid import uuid4

    with pytest.raises(NotFoundError):
        await cycle_service.assert_open(uuid4())


async def test_assert_open_success(
    cycle_service: Any,
    fake_session: FakeSession,
) -> None:
    """``assert_open`` is a no-op for Open cycles."""
    cycle = make_cycle(status=CycleState.open)
    fake_session.cycles.append(cycle)
    await cycle_service.assert_open(cycle.id)
