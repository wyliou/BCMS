"""Unit tests for :class:`app.domain.templates.service.TemplateService`.

These tests drive the service against the in-memory :class:`FakeSession`
from ``conftest.py``. Storage I/O is monkey-patched per test — the
happy path stores bytes in a module-level dict keyed by the returned
opaque key; failure tests raise on demand.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from app.core.errors import ForbiddenError, NotFoundError
from app.core.security.roles import Role
from app.domain.audit.actions import AuditAction
from app.domain.templates import service as service_module
from app.domain.templates.models import TemplateStatus
from app.domain.templates.service import TemplateService
from tests.unit.templates.conftest import (
    FakeAudit,
    FakeSession,
    make_account,
    make_actual,
    make_cycle,
    make_org_unit,
    make_user,
)


# --------------------------------------------------------------------- helpers
class _FakeStorage:
    """Capture-and-replay storage stand-in.

    Attributes:
        files: ``storage_key -> raw_bytes`` map.
        save_calls: List of ``(category, filename, content_length)``.
        save_failures: A queue of exceptions — each :meth:`save` call
            pops one; an empty queue behaves normally.
    """

    def __init__(self) -> None:
        """Initialize empty stores."""
        self.files: dict[str, bytes] = {}
        self.save_calls: list[tuple[str, str, int]] = []
        self.save_failures: list[Exception] = []
        self._counter = 0

    async def save(self, category: str, filename: str, content: bytes) -> str:
        """Fake :func:`app.infra.storage.save`."""
        self.save_calls.append((category, filename, len(content)))
        if self.save_failures:
            exc = self.save_failures.pop(0)
            raise exc
        self._counter += 1
        key = f"templates/test/{self._counter:04d}_{filename}"
        self.files[key] = bytes(content)
        return key

    async def read(self, storage_key: str) -> bytes:
        """Fake :func:`app.infra.storage.read`."""
        return self.files[storage_key]


@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> _FakeStorage:
    """Patch ``storage_save`` / ``storage_read`` on the service module."""
    fake = _FakeStorage()
    monkeypatch.setattr(service_module, "storage_save", fake.save)
    monkeypatch.setattr(service_module, "storage_read", fake.read)
    return fake


def _make_service(session: FakeSession) -> tuple[TemplateService, FakeAudit]:
    """Wire a service + fake audit on ``session`` and return both."""
    service = TemplateService(session)  # type: ignore[arg-type]
    audit = FakeAudit()
    service._audit = audit  # type: ignore[assignment]
    return service, audit


# --------------------------------------------------------------------- generate_for_cycle
async def test_generate_for_cycle_all_units_succeed(
    fake_session: FakeSession, fake_storage: _FakeStorage
) -> None:
    """Happy path: three filing units all generate cleanly (FR-009)."""
    cycle = make_cycle()
    fake_session.cycles[cycle.id] = cycle

    units = [make_org_unit(code=code) for code in ("4001", "4002", "4003")]
    fake_session.org_units.extend(units)

    operational = [make_account(code=c) for c in ("5101", "5102")]
    fake_session.account_codes.extend(operational)

    service, audit = _make_service(fake_session)
    user = make_user(role=Role.FinanceAdmin)

    results = await service.generate_for_cycle(
        cycle=cycle,
        filing_units=units,
        user=user,
    )

    assert len(results) == 3
    assert {r.status for r in results} == {"generated"}
    assert len(fake_session.excel_templates) == 3
    assert len(fake_storage.save_calls) == 3
    assert all(call[0] == "templates" for call in fake_storage.save_calls)
    assert len(audit.events) == 3
    assert all(event["action"] == AuditAction.TEMPLATE_GENERATE for event in audit.events)


async def test_generate_for_cycle_per_unit_failure_isolated(
    fake_session: FakeSession, fake_storage: _FakeStorage
) -> None:
    """A storage failure on unit 2 must NOT abort units 1 and 3 (FR-009)."""
    cycle = make_cycle()
    fake_session.cycles[cycle.id] = cycle

    units = [make_org_unit(code=code) for code in ("4001", "4002", "4003")]
    fake_session.org_units.extend(units)
    fake_session.account_codes.append(make_account(code="5101"))

    # Reason: inject one failure — hit the second save only.
    fake_storage.save_failures = [RuntimeError("storage boom")]

    # The first save call should succeed, so prepend a "pass" then fail.
    async def _save_patched(category: str, filename: str, content: bytes) -> str:
        fake_storage.save_calls.append((category, filename, len(content)))
        # fail only on the second call
        if len(fake_storage.save_calls) == 2:
            raise RuntimeError("storage boom")
        fake_storage._counter += 1
        key = f"templates/test/{fake_storage._counter:04d}_{filename}"
        fake_storage.files[key] = bytes(content)
        return key

    import app.domain.templates.service as svc

    original = svc.storage_save
    svc.storage_save = _save_patched  # type: ignore[assignment]
    try:
        service, _audit = _make_service(fake_session)
        results = await service.generate_for_cycle(
            cycle=cycle,
            filing_units=units,
            user=make_user(),
        )
    finally:
        svc.storage_save = original  # type: ignore[assignment]

    assert [r.status for r in results] == ["generated", "error", "generated"]
    assert results[1].error is not None
    assert "storage boom" in (results[1].error or "")
    # Two successful templates + one error row = 3 rows total.
    assert len(fake_session.excel_templates) == 3
    statuses = {row.status for row in fake_session.excel_templates}
    assert statuses == {TemplateStatus.generated, TemplateStatus.error}


async def test_generate_for_cycle_zero_actuals_still_generates(
    fake_session: FakeSession, fake_storage: _FakeStorage
) -> None:
    """CR-034: empty ``actual_expenses`` still yields a generated row."""
    cycle = make_cycle()
    fake_session.cycles[cycle.id] = cycle
    unit = make_org_unit()
    fake_session.org_units.append(unit)
    fake_session.account_codes.append(make_account(code="5101"))

    service, _audit = _make_service(fake_session)
    results = await service.generate_for_cycle(
        cycle=cycle,
        filing_units=[unit],
        user=make_user(),
    )

    assert len(results) == 1
    assert results[0].status == "generated"
    assert len(fake_session.excel_templates) == 1


async def test_generate_for_cycle_with_prior_actuals(
    fake_session: FakeSession, fake_storage: _FakeStorage
) -> None:
    """Existing actuals are fetched and fed into the builder."""
    cycle = make_cycle()
    fake_session.cycles[cycle.id] = cycle
    unit = make_org_unit()
    fake_session.org_units.append(unit)
    account = make_account(code="5101")
    fake_session.account_codes.append(account)
    fake_session.actual_expenses.append(
        make_actual(
            cycle_id=cycle.id,
            org_unit_id=unit.id,
            account_id=account.id,
            amount=Decimal("1234.56"),
        )
    )

    service, _audit = _make_service(fake_session)
    results = await service.generate_for_cycle(
        cycle=cycle,
        filing_units=[unit],
        user=make_user(),
    )

    assert results[0].status == "generated"
    assert len(fake_storage.save_calls) == 1


# --------------------------------------------------------------------- regenerate
async def test_regenerate_replaces_existing_row(
    fake_session: FakeSession, fake_storage: _FakeStorage
) -> None:
    """Regenerate deletes the prior row and inserts a fresh one."""
    cycle = make_cycle()
    fake_session.cycles[cycle.id] = cycle
    unit = make_org_unit()
    fake_session.org_units.append(unit)
    fake_session.account_codes.append(make_account(code="5101"))

    service, _audit = _make_service(fake_session)
    user = make_user()

    first = await service.generate_for_cycle(
        cycle=cycle,
        filing_units=[unit],
        user=user,
    )
    assert len(fake_session.excel_templates) == 1
    first_template_id = first[0].template_id

    second_result = await service.regenerate(cycle=cycle, org_unit=unit, user=user)
    assert second_result.status == "generated"
    assert len(fake_session.excel_templates) == 1  # still only one row
    assert fake_session.excel_templates[0].id != first_template_id


# --------------------------------------------------------------------- download
async def _seed_generated_template(
    *,
    session: FakeSession,
    storage: _FakeStorage,
) -> Any:
    """Populate one generated template row and return ``(cycle, unit, user)``."""
    cycle = make_cycle()
    session.cycles[cycle.id] = cycle
    unit = make_org_unit()
    session.org_units.append(unit)
    session.account_codes.append(make_account(code="5101"))
    service, audit = _make_service(session)
    user = make_user(role=Role.SystemAdmin)
    await service.generate_for_cycle(cycle=cycle, filing_units=[unit], user=user)
    return cycle, unit, user, service, audit


async def test_download_happy_path_increments_count(
    fake_session: FakeSession, fake_storage: _FakeStorage
) -> None:
    """Download reads bytes, bumps counter, records TEMPLATE_DOWNLOAD audit."""
    cycle, unit, user, service, audit = await _seed_generated_template(
        session=fake_session, storage=fake_storage
    )
    # Drop the generate audit events.
    audit.events.clear()

    filename, content = await service.download(
        cycle_id=cycle.id,
        org_unit_id=unit.id,
        user=user,
    )
    assert filename == f"{unit.code}_{cycle.fiscal_year}_budget_template.xlsx"
    assert content  # non-empty workbook bytes

    template = fake_session.excel_templates[0]
    assert template.download_count == 1
    assert any(event["action"] == AuditAction.TEMPLATE_DOWNLOAD for event in audit.events)

    # A second download bumps again.
    await service.download(cycle_id=cycle.id, org_unit_id=unit.id, user=user)
    assert template.download_count == 2


async def test_download_missing_template_raises_tpl_002(
    fake_session: FakeSession, fake_storage: _FakeStorage
) -> None:
    """No row → TPL_002."""
    cycle = make_cycle()
    fake_session.cycles[cycle.id] = cycle
    unit = make_org_unit()
    fake_session.org_units.append(unit)
    service, _audit = _make_service(fake_session)

    with pytest.raises(NotFoundError) as excinfo:
        await service.download(
            cycle_id=cycle.id,
            org_unit_id=unit.id,
            user=make_user(role=Role.SystemAdmin),
        )
    assert excinfo.value.code == "TPL_002"


async def test_download_error_row_raises_tpl_002(
    fake_session: FakeSession, fake_storage: _FakeStorage
) -> None:
    """An error-state row must also raise TPL_002."""
    cycle = make_cycle()
    fake_session.cycles[cycle.id] = cycle
    unit = make_org_unit()
    fake_session.org_units.append(unit)
    fake_session.account_codes.append(make_account(code="5101"))

    # Force a generate failure to seed an error row.
    import app.domain.templates.service as svc

    original = svc.storage_save

    async def _always_fail(*_a: Any, **_kw: Any) -> str:
        raise RuntimeError("nope")

    svc.storage_save = _always_fail  # type: ignore[assignment]
    try:
        service, _audit = _make_service(fake_session)
        await service.generate_for_cycle(
            cycle=cycle,
            filing_units=[unit],
            user=make_user(),
        )
    finally:
        svc.storage_save = original  # type: ignore[assignment]

    assert len(fake_session.excel_templates) == 1
    assert fake_session.excel_templates[0].status == TemplateStatus.error

    service, _audit = _make_service(fake_session)
    with pytest.raises(NotFoundError) as excinfo:
        await service.download(
            cycle_id=cycle.id,
            org_unit_id=unit.id,
            user=make_user(role=Role.SystemAdmin),
        )
    assert excinfo.value.code == "TPL_002"


async def test_download_wrong_scope_raises_rbac_002(
    fake_session: FakeSession, fake_storage: _FakeStorage
) -> None:
    """A FilingUnitManager on a different unit gets RBAC_002."""
    cycle, unit, _admin_user, service, _audit = await _seed_generated_template(
        session=fake_session, storage=fake_storage
    )

    # Build a FilingUnitManager whose scope is a DIFFERENT org unit.
    other_unit = make_org_unit(code="9999", name="Other")
    fake_session.org_units.append(other_unit)
    scoped_user = make_user(role=Role.FilingUnitManager)
    scoped_user.org_unit_id = other_unit.id

    with pytest.raises(ForbiddenError) as excinfo:
        await service.download(
            cycle_id=cycle.id,
            org_unit_id=unit.id,
            user=scoped_user,
        )
    assert excinfo.value.code == "RBAC_002"
