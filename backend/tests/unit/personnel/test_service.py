"""Unit tests for :class:`PersonnelImportService` (FR-024..FR-026)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.core.errors import AppError, BatchValidationError
from app.core.security.roles import Role
from app.domain.audit.actions import AuditAction
from app.domain.personnel import service as service_module
from app.domain.personnel.service import PersonnelImportService
from tests.unit.personnel.conftest import (
    FakeAccountService,
    FakeAudit,
    FakeCycleService,
    FakeNotificationService,
    FakeSession,
    FakeStorage,
    build_valid_csv,
    make_account,
    make_cycle,
    make_org_unit,
    make_user,
)

PERSONNEL_CODES = {"HR001", "HR002", "HR003"}


# ----------------------------------------------------------------- helpers
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
    personnel_codes: set[str] = PERSONNEL_CODES,
    notifications: FakeNotificationService | None = None,
) -> tuple[PersonnelImportService, FakeAudit, FakeCycleService]:
    """Wire a service with fake collaborators and return handles."""
    service = PersonnelImportService(session, notifications=notifications)  # type: ignore[arg-type]
    audit = FakeAudit()
    cycles = FakeCycleService(open_cycles=set(open_cycle_ids))
    accounts = FakeAccountService(codes=personnel_codes)
    service._audit = audit  # type: ignore[assignment]
    service._cycles = cycles  # type: ignore[assignment]
    service._accounts = accounts  # type: ignore[assignment]
    return service, audit, cycles


def _seed(
    session: FakeSession,
    *,
    codes: list[str] | None = None,
) -> tuple[Any, Any]:
    """Populate the fake session with a cycle, org units, and account codes."""
    cycle = make_cycle()
    session.cycles[cycle.id] = cycle
    unit = make_org_unit(code="4023")
    session.org_units.append(unit)
    for code in codes or list(PERSONNEL_CODES):
        session.account_codes.append(make_account(code=code))
    return cycle, unit


# ================================================================ happy path
async def test_import_success_creates_version_1(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """Valid CSV, Open cycle → version=1, lines in DB, audit recorded."""
    cycle, unit = _seed(fake_session)
    notifications = FakeNotificationService()
    # Add a FinanceAdmin user so notifications are attempted.
    finance_user = make_user(role=Role.FinanceAdmin, email="finance@example.com")
    fake_session.users.append(finance_user)

    service, audit, _cycles = _build_service(
        fake_session,
        open_cycle_ids={cycle.id},
        notifications=notifications,
    )
    user = make_user(role=Role.HRAdmin)

    content = build_valid_csv(
        rows=[
            ("4023", "HR001", 1000),
            ("4023", "HR002", 2000),
        ]
    )
    upload = await service.import_(
        cycle_id=cycle.id,
        filename="personnel.csv",
        content=content,
        user=user,
    )

    assert upload.version == 1
    assert len(fake_session.personnel_uploads) == 1
    assert len(fake_session.personnel_lines) == 2
    assert fake_storage.save_calls[0][0] == "personnel"
    # CR-006: audit was recorded.
    assert any(event["action"] == AuditAction.PERSONNEL_IMPORT for event in audit.events)
    # Notification sent to FinanceAdmin (CR-029 success path).
    assert len(notifications.batch_calls) == 1
    batch_call = notifications.batch_calls[0]
    assert batch_call["recipients"][0][0] == finance_user.id


async def test_import_second_version_increments(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """Two imports for the same cycle → second has version=2."""
    cycle, unit = _seed(fake_session)
    service, _audit, _cycles = _build_service(
        fake_session,
        open_cycle_ids={cycle.id},
    )
    user = make_user(role=Role.HRAdmin)
    content = build_valid_csv(rows=[("4023", "HR001", 500)])

    upload1 = await service.import_(
        cycle_id=cycle.id,
        filename="v1.csv",
        content=content,
        user=user,
    )
    upload2 = await service.import_(
        cycle_id=cycle.id,
        filename="v2.csv",
        content=content,
        user=user,
    )

    assert upload1.version == 1
    assert upload2.version == 2
    assert len(fake_session.personnel_uploads) == 2


# ================================================================ cycle closed
async def test_import_cycle_closed_raises_cycle_004(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """Closed cycle → CYCLE_004 before file parsing; nothing persisted (CR-005)."""
    cycle, unit = _seed(fake_session)
    service, audit, _cycles = _build_service(
        fake_session,
        open_cycle_ids=set(),  # no open cycles
    )
    user = make_user(role=Role.HRAdmin)
    content = build_valid_csv(rows=[("4023", "HR001", 500)])

    with pytest.raises(AppError) as excinfo:
        await service.import_(
            cycle_id=cycle.id,
            filename="personnel.csv",
            content=content,
            user=user,
        )
    assert excinfo.value.code == "CYCLE_004"
    assert fake_storage.save_calls == []
    assert len(fake_session.personnel_uploads) == 0
    assert audit.events == []


# ================================================================ validation failure
async def test_import_invalid_row_zero_persisted(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """Unknown dept_id → BatchValidationError(PERS_004); DB unchanged (CR-004)."""
    cycle, unit = _seed(fake_session)
    service, audit, _cycles = _build_service(
        fake_session,
        open_cycle_ids={cycle.id},
    )
    user = make_user(role=Role.HRAdmin)
    content = build_valid_csv(rows=[("UNKNOWN_DEPT", "HR001", 500)])

    with pytest.raises(BatchValidationError) as excinfo:
        await service.import_(
            cycle_id=cycle.id,
            filename="bad.csv",
            content=content,
            user=user,
        )
    assert excinfo.value.code == "PERS_004"
    assert len(fake_session.personnel_uploads) == 0
    assert len(fake_session.personnel_lines) == 0
    # No storage, no audit (nothing committed).
    assert fake_storage.save_calls == []
    assert audit.events == []


# ================================================================ notification failure
async def test_import_notification_failure_does_not_invalidate(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """SMTP failure still returns the persisted upload (CR-029)."""
    cycle, unit = _seed(fake_session)
    notifications = FakeNotificationService()
    notifications.fail = True
    finance_user = make_user(role=Role.FinanceAdmin, email="finance@example.com")
    fake_session.users.append(finance_user)

    service, audit, _cycles = _build_service(
        fake_session,
        open_cycle_ids={cycle.id},
        notifications=notifications,
    )
    user = make_user(role=Role.HRAdmin)
    content = build_valid_csv(rows=[("4023", "HR001", 1000)])

    # Import must succeed even when SMTP raises.
    upload = await service.import_(
        cycle_id=cycle.id,
        filename="personnel.csv",
        content=content,
        user=user,
    )
    assert upload is not None
    assert len(fake_session.personnel_uploads) == 1
    # Notification was attempted (batch_calls recorded before fail).
    assert len(notifications.batch_calls) == 1


# ================================================================ list_versions
async def test_list_versions_sorted_ascending(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """list_versions returns uploads ordered by version ascending."""
    cycle, unit = _seed(fake_session)
    service, _audit, _cycles = _build_service(
        fake_session,
        open_cycle_ids={cycle.id},
    )
    user = make_user(role=Role.HRAdmin)
    content = build_valid_csv(rows=[("4023", "HR001", 500)])

    await service.import_(cycle_id=cycle.id, filename="v1.csv", content=content, user=user)
    await service.import_(cycle_id=cycle.id, filename="v2.csv", content=content, user=user)
    await service.import_(cycle_id=cycle.id, filename="v3.csv", content=content, user=user)

    versions = await service.list_versions(cycle.id)
    assert [v.version for v in versions] == [1, 2, 3]


# ================================================================ get / NotFoundError
async def test_get_returns_upload(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """get() returns an existing upload row."""
    cycle, unit = _seed(fake_session)
    service, _audit, _cycles = _build_service(
        fake_session,
        open_cycle_ids={cycle.id},
    )
    user = make_user(role=Role.HRAdmin)
    content = build_valid_csv(rows=[("4023", "HR001", 500)])

    upload = await service.import_(cycle_id=cycle.id, filename="p.csv", content=content, user=user)
    fetched = await service.get(upload.id)
    assert fetched.id == upload.id


async def test_get_not_found_raises(
    fake_session: FakeSession,
) -> None:
    """get() raises NotFoundError for an unknown id."""
    from app.core.errors import NotFoundError

    service = PersonnelImportService(fake_session)  # type: ignore[arg-type]
    with pytest.raises(NotFoundError) as excinfo:
        await service.get(uuid4())
    assert excinfo.value.code == "PERS_004"


# ================================================================ get_latest_by_cycle
async def test_get_latest_by_cycle_aggregates_lines(
    fake_session: FakeSession,
    fake_storage: FakeStorage,
) -> None:
    """get_latest_by_cycle returns dict keyed by (org_unit_id, account_code_id)."""
    cycle, unit = _seed(fake_session)
    service, _audit, _cycles = _build_service(
        fake_session,
        open_cycle_ids={cycle.id},
    )
    user = make_user(role=Role.HRAdmin)
    content = build_valid_csv(rows=[("4023", "HR001", 1000), ("4023", "HR002", 500)])

    await service.import_(cycle_id=cycle.id, filename="p.csv", content=content, user=user)

    amounts = await service.get_latest_by_cycle(cycle.id)
    # Should have 2 keys — one per account code.
    assert len(amounts) == 2


async def test_get_latest_by_cycle_empty_cycle(
    fake_session: FakeSession,
) -> None:
    """get_latest_by_cycle returns empty dict when no uploads exist."""
    service = PersonnelImportService(fake_session)  # type: ignore[arg-type]
    amounts = await service.get_latest_by_cycle(uuid4())
    assert amounts == {}
