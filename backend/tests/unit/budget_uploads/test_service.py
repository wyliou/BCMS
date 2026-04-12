"""Unit tests for :class:`BudgetUploadService` (FR-011..FR-013)."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.errors import AppError, BatchValidationError, ForbiddenError
from app.core.security.roles import Role
from app.domain.audit.actions import AuditAction
from app.domain.budget_uploads import service as service_module
from app.domain.budget_uploads.service import BudgetUploadService
from tests.unit.budget_uploads.conftest import (
    FakeAccountService,
    FakeAudit,
    FakeCycleService,
    FakeNotificationService,
    FakeSession,
    FakeStorage,
    build_valid_workbook,
    make_account,
    make_cycle,
    make_org_unit,
    make_user,
)

OPERATIONAL = {"5101", "5102", "5103"}


# --------------------------------------------------------------------- helpers
@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> FakeStorage:
    """Patch ``storage_module.save`` on the service module."""
    storage = FakeStorage()

    async def _save(category: str, filename: str, content: bytes) -> str:
        return await storage.save(category, filename, content)

    class _StorageProxy:
        save = staticmethod(_save)

    monkeypatch.setattr(service_module, "storage_module", _StorageProxy)
    return storage


def _build_service(
    session: FakeSession,
    *,
    open_cycle_ids: set[Any],
    operational_codes: set[str] = OPERATIONAL,
    notifications: FakeNotificationService | None = None,
) -> tuple[BudgetUploadService, FakeAudit, FakeCycleService]:
    """Wire a service with fake collaborators and return handles."""
    service = BudgetUploadService(session, notifications=notifications)  # type: ignore[arg-type]
    audit = FakeAudit()
    cycles = FakeCycleService(open_cycles=set(open_cycle_ids))
    accounts = FakeAccountService(codes=operational_codes)
    service._audit = audit  # type: ignore[assignment]
    service._cycles = cycles  # type: ignore[assignment]
    service._accounts = accounts  # type: ignore[assignment]
    return service, audit, cycles


def _seed(session: FakeSession, *, code: str = "4023") -> tuple[Any, Any]:
    """Populate the fake session with a cycle, org unit, and account codes."""
    cycle = make_cycle()
    session.cycles[cycle.id] = cycle
    unit = make_org_unit(code=code)
    session.org_units.append(unit)
    for account_code in OPERATIONAL:
        session.account_codes.append(make_account(code=account_code))
    return cycle, unit


# --------------------------------------------------------------------- happy
async def test_upload_happy_path_persists_rows_and_audits(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """Valid upload creates version 1, budget lines, audit, and notification."""
    cycle, unit = _seed(fake_session)
    notifications = FakeNotificationService()
    service, audit, _cycles = _build_service(
        fake_session, open_cycle_ids={cycle.id}, notifications=notifications
    )
    user = make_user(role=Role.FilingUnitManager, org_unit_id=unit.id)

    content = build_valid_workbook(
        dept_code="4023",
        rows=[("5101", "A", "0", 100), ("5102", "B", "0", 0)],
    )
    upload = await service.upload(
        cycle_id=cycle.id,
        org_unit_id=unit.id,
        filename="q1.xlsx",
        content=content,
        user=user,
    )

    assert upload.version == 1
    assert upload.row_count == 2
    assert upload.status == "valid"
    assert len(fake_session.budget_uploads) == 1
    assert len(fake_session.budget_lines) == 2
    assert fake_storage.save_calls[0][0] == "budget_uploads"
    assert any(event["action"] == AuditAction.BUDGET_UPLOAD for event in audit.events)
    assert len(notifications.calls) == 1
    assert notifications.calls[0]["recipient_user_id"] == user.id


# --------------------------------------------------------------- closed cycle
async def test_upload_closed_cycle_raises_cycle_004(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """Closed cycle short-circuits before any file I/O or audit."""
    cycle, unit = _seed(fake_session)
    # Do NOT mark cycle Open in the fake cycle service.
    service, audit, cycles = _build_service(fake_session, open_cycle_ids=set())
    user = make_user(role=Role.FilingUnitManager, org_unit_id=unit.id)

    content = build_valid_workbook(
        dept_code="4023",
        rows=[("5101", "A", "0", 1)],
    )
    with pytest.raises(AppError) as excinfo:
        await service.upload(
            cycle_id=cycle.id,
            org_unit_id=unit.id,
            filename="q1.xlsx",
            content=content,
            user=user,
        )
    assert excinfo.value.code == "CYCLE_004"
    assert fake_storage.save_calls == []
    assert len(fake_session.budget_uploads) == 0
    assert audit.events == []


# ------------------------------------------------------------- scope mismatch
async def test_upload_scope_mismatch_raises_rbac_002(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """Filing unit manager for unit A cannot upload to unit B."""
    cycle, unit_a = _seed(fake_session, code="4023")
    unit_b = make_org_unit(code="4099")
    fake_session.org_units.append(unit_b)

    service, _audit, _cycles = _build_service(fake_session, open_cycle_ids={cycle.id})
    user = make_user(role=Role.FilingUnitManager, org_unit_id=unit_a.id)

    content = build_valid_workbook(
        dept_code="4099",
        rows=[("5101", "A", "0", 1)],
    )
    with pytest.raises(ForbiddenError) as excinfo:
        await service.upload(
            cycle_id=cycle.id,
            org_unit_id=unit_b.id,  # target unit B
            filename="q1.xlsx",
            content=content,
            user=user,
        )
    assert excinfo.value.code == "RBAC_002"
    assert fake_storage.save_calls == []
    assert len(fake_session.budget_uploads) == 0


# ------------------------------------------------------- validation rollback
async def test_upload_validation_failure_persists_nothing(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """Row errors cause ``BatchValidationError`` and zero rows persisted (CR-004)."""
    cycle, unit = _seed(fake_session)
    service, audit, _cycles = _build_service(fake_session, open_cycle_ids={cycle.id})
    user = make_user(role=Role.FilingUnitManager, org_unit_id=unit.id)

    content = build_valid_workbook(
        dept_code="4023",
        rows=[
            ("5101", "A", "0", "abc"),  # UPLOAD_005
            ("5102", "B", "0", -5),  # UPLOAD_006
        ],
    )
    with pytest.raises(BatchValidationError) as excinfo:
        await service.upload(
            cycle_id=cycle.id,
            org_unit_id=unit.id,
            filename="q1.xlsx",
            content=content,
            user=user,
        )
    assert excinfo.value.code == "UPLOAD_007"
    assert len(fake_session.budget_uploads) == 0
    assert len(fake_session.budget_lines) == 0
    assert fake_storage.save_calls == []
    assert audit.events == []


# ------------------------------------------------------- notification failure
async def test_upload_notification_failure_does_not_invalidate(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """SMTP failure still returns the persisted upload (CR-029)."""
    cycle, unit = _seed(fake_session)
    notifications = FakeNotificationService()
    notifications.fail = True
    service, audit, _cycles = _build_service(
        fake_session, open_cycle_ids={cycle.id}, notifications=notifications
    )
    user = make_user(role=Role.FilingUnitManager, org_unit_id=unit.id)

    content = build_valid_workbook(
        dept_code="4023",
        rows=[("5101", "A", "0", 10)],
    )
    upload = await service.upload(
        cycle_id=cycle.id,
        org_unit_id=unit.id,
        filename="q1.xlsx",
        content=content,
        user=user,
    )

    assert upload.version == 1
    assert len(fake_session.budget_uploads) == 1
    assert notifications.calls  # send was attempted
    # BUDGET_UPLOAD audit still recorded.
    assert any(event["action"] == AuditAction.BUDGET_UPLOAD for event in audit.events)


# ------------------------------------------------------ version monotonicity
async def test_upload_version_increments_across_uploads(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """Three uploads for one pair produce version 1, 2, 3."""
    cycle, unit = _seed(fake_session)
    service, _audit, _cycles = _build_service(fake_session, open_cycle_ids={cycle.id})
    user = make_user(role=Role.FilingUnitManager, org_unit_id=unit.id)

    content = build_valid_workbook(
        dept_code="4023",
        rows=[("5101", "A", "0", 1)],
    )
    versions: list[int] = []
    for _ in range(3):
        upload = await service.upload(
            cycle_id=cycle.id,
            org_unit_id=unit.id,
            filename="q1.xlsx",
            content=content,
            user=user,
        )
        versions.append(upload.version)

    assert versions == [1, 2, 3]
    assert len(fake_session.budget_uploads) == 3
    assert len(fake_session.budget_lines) == 3


async def test_list_versions_orders_desc(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """``list_versions`` returns rows newest-first."""
    cycle, unit = _seed(fake_session)
    service, _audit, _cycles = _build_service(fake_session, open_cycle_ids={cycle.id})
    user = make_user(role=Role.FilingUnitManager, org_unit_id=unit.id)

    content = build_valid_workbook(
        dept_code="4023",
        rows=[("5101", "A", "0", 1)],
    )
    for _ in range(3):
        await service.upload(
            cycle_id=cycle.id,
            org_unit_id=unit.id,
            filename="q.xlsx",
            content=content,
            user=user,
        )

    rows = await service.list_versions(cycle_id=cycle.id, org_unit_id=unit.id)
    assert [r.version for r in rows] == [3, 2, 1]


async def test_get_latest_by_cycle_aggregates(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """``get_latest_by_cycle`` maps ``(org_unit, account) → latest amount``."""
    cycle, unit = _seed(fake_session)
    service, _audit, _cycles = _build_service(fake_session, open_cycle_ids={cycle.id})
    user = make_user(role=Role.FilingUnitManager, org_unit_id=unit.id)

    v1 = build_valid_workbook(
        dept_code="4023",
        rows=[("5101", "A", "0", 100)],
    )
    v2 = build_valid_workbook(
        dept_code="4023",
        rows=[("5101", "A", "0", 250), ("5102", "B", "0", 75)],
    )
    await service.upload(
        cycle_id=cycle.id,
        org_unit_id=unit.id,
        filename="q1.xlsx",
        content=v1,
        user=user,
    )
    await service.upload(
        cycle_id=cycle.id,
        org_unit_id=unit.id,
        filename="q2.xlsx",
        content=v2,
        user=user,
    )

    result = await service.get_latest_by_cycle(cycle.id)

    # Only the v=2 upload's lines should appear.
    assert len(result) == 2
    account_5101_id = next(a.id for a in fake_session.account_codes if a.code == "5101")
    assert result[(unit.id, account_5101_id)] == 250
