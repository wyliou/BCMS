"""Unit tests for :mod:`app.domain.shared_costs.service`.

Covers:
- ``diff_affected_units`` pure-function behaviour.
- ``SharedCostImportService.import_`` happy path and error paths.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from app.core.errors import AppError, BatchValidationError
from app.domain.shared_costs.models import SharedCostLine, SharedCostUpload
from app.domain.shared_costs.service import SharedCostImportService, diff_affected_units
from tests.unit.shared_costs.conftest import (
    FakeAccountService,
    FakeAudit,
    FakeCycleService,
    FakeNotificationService,
    FakeSession,
    FakeStorage,
    build_csv_content,
    make_account,
    make_cycle,
    make_org_unit,
    make_user,
)

# ===========================================================================
#                   diff_affected_units  (pure function)
# ===========================================================================


def _make_line(
    org_unit_id: UUID,
    account_code_id: UUID,
    amount: Decimal,
) -> SharedCostLine:
    """Create a minimal SharedCostLine without a database."""
    line = SharedCostLine(
        upload_id=uuid4(),
        org_unit_id=org_unit_id,
        account_code_id=account_code_id,
        amount=amount,
    )
    line.id = uuid4()
    return line


def test_diff_empty_prev_all_new_affected() -> None:
    """Empty prev → every new org unit is affected (first-version case)."""
    unit_a = uuid4()
    unit_b = uuid4()
    code = uuid4()
    new_lines = [
        _make_line(unit_a, code, Decimal("100")),
        _make_line(unit_b, code, Decimal("200")),
    ]
    result = diff_affected_units([], new_lines)

    assert unit_a in result
    assert unit_b in result
    assert len(result) == 2


def test_diff_changed_amount_is_affected() -> None:
    """Amount change on one org unit → that unit is in the diff."""
    unit_a = uuid4()
    code = uuid4()
    prev = [_make_line(unit_a, code, Decimal("100"))]
    new = [_make_line(unit_a, code, Decimal("200"))]

    result = diff_affected_units(prev, new)

    assert unit_a in result


def test_diff_unchanged_not_included() -> None:
    """Identical prev and new → empty set returned."""
    unit_a = uuid4()
    code = uuid4()
    prev = [_make_line(unit_a, code, Decimal("100"))]
    new = [_make_line(unit_a, code, Decimal("100"))]

    result = diff_affected_units(prev, new)

    assert len(result) == 0
    assert unit_a not in result


def test_diff_new_department_is_affected() -> None:
    """New department in new version is in the diff."""
    unit_a = uuid4()
    unit_b = uuid4()
    code = uuid4()
    prev = [_make_line(unit_a, code, Decimal("100"))]
    new = [
        _make_line(unit_a, code, Decimal("100")),
        _make_line(unit_b, code, Decimal("50")),
    ]

    result = diff_affected_units(prev, new)

    assert unit_b in result
    assert unit_a not in result  # unchanged


def test_diff_removed_department_is_affected() -> None:
    """Department in prev but not new → in diff."""
    unit_a = uuid4()
    unit_b = uuid4()
    code = uuid4()
    prev = [
        _make_line(unit_a, code, Decimal("100")),
        _make_line(unit_b, code, Decimal("200")),
    ]
    new = [_make_line(unit_a, code, Decimal("100"))]

    result = diff_affected_units(prev, new)

    assert unit_b in result
    assert unit_a not in result


def test_diff_multiple_accounts_same_unit_one_changed() -> None:
    """Multiple accounts for same unit, only one changed → unit in diff once."""
    unit_a = uuid4()
    code1 = uuid4()
    code2 = uuid4()
    prev = [
        _make_line(unit_a, code1, Decimal("100")),
        _make_line(unit_a, code2, Decimal("200")),
    ]
    new = [
        _make_line(unit_a, code1, Decimal("150")),  # changed
        _make_line(unit_a, code2, Decimal("200")),  # unchanged
    ]
    # Total prev = 300, total new = 350 → affected
    result = diff_affected_units(prev, new)

    assert unit_a in result
    assert len(result) == 1


# ===========================================================================
#               SharedCostImportService.import_ — unit (mocked)
# ===========================================================================


def _build_service(
    session: FakeSession,
    *,
    cycle_id: UUID | None = None,
    shared_cost_codes: set[str] | None = None,
    notification_service: FakeNotificationService | None = None,
) -> tuple[SharedCostImportService, FakeAudit, FakeCycleService, FakeStorage]:
    """Construct a service wired with fakes.

    Returns:
        tuple: (service, fake_audit, fake_cycles, fake_storage).
    """
    if cycle_id is None:
        cycle_id = uuid4()
    fake_audit = FakeAudit()
    fake_cycles = FakeCycleService(open_cycles={cycle_id})
    fake_accounts = FakeAccountService(codes=shared_cost_codes or {"SC001", "SC002"})
    fake_storage = FakeStorage()

    svc = SharedCostImportService(session, notifications=notification_service)
    # Wire fakes
    svc._cycles = fake_cycles  # type: ignore[assignment]
    svc._accounts = fake_accounts  # type: ignore[assignment]
    svc._audit = fake_audit  # type: ignore[assignment]

    return svc, fake_audit, fake_cycles, fake_storage


@pytest.mark.asyncio
async def test_import_happy_path() -> None:
    """Valid CSV → upload inserted, lines persisted, audit recorded, upload returned."""
    session = FakeSession()
    cycle = make_cycle()
    session.cycles[cycle.id] = cycle
    unit = make_org_unit(code="4023")
    session.org_units.append(unit)

    # Seed account_code rows
    acc = make_account(code="SC001")
    session.account_codes.append(acc)

    content = build_csv_content([("4023", "SC001", "1000")])
    user = make_user()

    svc, fake_audit, _, fake_storage = _build_service(
        session,
        cycle_id=cycle.id,
        shared_cost_codes={"SC001"},
    )

    with patch("app.domain.shared_costs.service.storage_module", fake_storage):
        upload = await svc.import_(
            cycle_id=cycle.id,
            filename="shared_costs.csv",
            content=content,
            user=user,
        )

    assert isinstance(upload, SharedCostUpload)
    assert upload.version == 1
    assert upload.cycle_id == cycle.id
    assert session.commits >= 1

    # Lines persisted
    assert len(session.shared_cost_lines) == 1
    line = session.shared_cost_lines[0]
    assert line.org_unit_id == unit.id
    assert line.amount == Decimal("1000.00")

    # Audit recorded
    assert len(fake_audit.events) == 1
    assert fake_audit.events[0]["action"].value == "SHARED_COST_IMPORT"


@pytest.mark.asyncio
async def test_import_closed_cycle_raises_cycle_004() -> None:
    """Closed cycle raises CYCLE_004 before any parsing."""
    session = FakeSession()
    svc, _, _, _ = _build_service(session, cycle_id=uuid4())
    # cycle_id not in open_cycles → should raise

    with pytest.raises(AppError) as exc_info:
        await svc.import_(
            cycle_id=uuid4(),  # unknown → not open
            filename="x.csv",
            content=b"dept_id,account_code,amount\n4023,SC001,1000",
            user=make_user(),
        )
    assert exc_info.value.code == "CYCLE_004"


@pytest.mark.asyncio
async def test_import_validation_failure_zero_persisted() -> None:
    """Invalid rows → BatchValidationError SHARED_004 and zero DB rows."""
    session = FakeSession()
    cycle = make_cycle()
    session.cycles[cycle.id] = cycle
    unit = make_org_unit(code="4023")
    session.org_units.append(unit)

    # dept_id=UNKNOWN is not in org_unit_codes → SHARED_001
    content = build_csv_content([("UNKNOWN_DEPT", "SC001", "1000")])
    user = make_user()

    svc, _, _, fake_storage = _build_service(
        session,
        cycle_id=cycle.id,
        shared_cost_codes={"SC001"},
    )

    with patch("app.domain.shared_costs.service.storage_module", fake_storage):
        with pytest.raises(BatchValidationError) as exc_info:
            await svc.import_(
                cycle_id=cycle.id,
                filename="bad.csv",
                content=content,
                user=user,
            )

    assert exc_info.value.code == "SHARED_004"
    # Zero rows persisted
    assert len(session.shared_cost_uploads) == 0
    assert len(session.shared_cost_lines) == 0


@pytest.mark.asyncio
async def test_import_notification_failure_upload_persisted() -> None:
    """Notification failure does NOT invalidate the import (CR-029)."""
    session = FakeSession()
    cycle = make_cycle()
    session.cycles[cycle.id] = cycle
    unit = make_org_unit(code="4023")
    session.org_units.append(unit)
    acc = make_account(code="SC001")
    session.account_codes.append(acc)

    # Add a manager user for the org unit
    manager = make_user(org_unit_id=unit.id)
    session.users.append(manager)

    content = build_csv_content([("4023", "SC001", "500")])
    user = make_user()

    fake_notif = FakeNotificationService()
    fake_notif.fail = True  # SMTP will fail

    svc, fake_audit, _, fake_storage = _build_service(
        session,
        cycle_id=cycle.id,
        shared_cost_codes={"SC001"},
        notification_service=fake_notif,
    )

    with patch("app.domain.shared_costs.service.storage_module", fake_storage):
        upload = await svc.import_(
            cycle_id=cycle.id,
            filename="shared_costs.csv",
            content=content,
            user=user,
        )

    # Upload persisted despite notification failure
    assert upload is not None
    assert len(session.shared_cost_uploads) == 1
    # Audit still recorded
    assert len(fake_audit.events) == 1


@pytest.mark.asyncio
async def test_import_version_increments() -> None:
    """Second import for same cycle gets version 2."""
    session = FakeSession()
    cycle = make_cycle()
    session.cycles[cycle.id] = cycle
    unit = make_org_unit(code="4023")
    session.org_units.append(unit)
    acc = make_account(code="SC001")
    session.account_codes.append(acc)

    content = build_csv_content([("4023", "SC001", "1000")])
    user = make_user()

    svc, _, _, fake_storage = _build_service(
        session,
        cycle_id=cycle.id,
        shared_cost_codes={"SC001"},
    )

    with patch("app.domain.shared_costs.service.storage_module", fake_storage):
        upload_v1 = await svc.import_(
            cycle_id=cycle.id,
            filename="v1.csv",
            content=content,
            user=user,
        )
        # Reset audit for second call
        svc._audit = FakeAudit()  # type: ignore[assignment]
        upload_v2 = await svc.import_(
            cycle_id=cycle.id,
            filename="v2.csv",
            content=content,
            user=user,
        )

    assert upload_v1.version == 1
    assert upload_v2.version == 2
