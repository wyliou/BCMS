"""Unit tests for :class:`ConsolidatedReportService` (FR-015, FR-016)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from app.domain.consolidation.report import ConsolidatedReportService, ReportScope
from app.domain.cycles.models import CycleState
from tests.unit.consolidation.conftest import (
    StubSession,
    make_account,
    make_cycle,
    make_org_unit,
)


def _install(
    service: ConsolidatedReportService,
    *,
    units: list[Any],
    accounts: dict[UUID, Any],
    budget_map: dict[tuple[UUID, UUID], Decimal],
    personnel_map: dict[tuple[UUID, UUID], Decimal] | None = None,
    shared_map: dict[tuple[UUID, UUID], Decimal] | None = None,
    actuals_map: dict[tuple[UUID, UUID], Decimal] | None = None,
) -> None:
    """Patch the service's collaborator calls + internal fetchers."""

    async def _budget(_cycle_id: Any) -> dict[tuple[UUID, UUID], Decimal]:
        return dict(budget_map)

    async def _personnel(_cycle_id: Any) -> dict[tuple[UUID, UUID], Decimal]:
        return dict(personnel_map or {})

    async def _shared(_cycle_id: Any) -> dict[tuple[UUID, UUID], Decimal]:
        return dict(shared_map or {})

    service._budget.get_latest_by_cycle = _budget  # type: ignore[assignment,method-assign]
    service._personnel.get_latest_by_cycle = _personnel  # type: ignore[assignment,method-assign]
    service._shared.get_latest_by_cycle = _shared  # type: ignore[assignment,method-assign]

    async def _actuals(*, cycle_id: Any) -> dict[tuple[UUID, UUID], Decimal]:
        return dict(actuals_map or {})

    async def _units(*, scope: Any) -> list[Any]:
        return list(units)

    async def _accounts(account_ids: set[UUID]) -> dict[UUID, Any]:
        return {aid: accounts[aid] for aid in account_ids if aid in accounts}

    async def _latest(_cycle_id: Any) -> Any:
        return None

    service._fetch_actuals = _actuals  # type: ignore[assignment,method-assign]
    service._fetch_org_units = _units  # type: ignore[assignment,method-assign]
    service._fetch_accounts = _accounts  # type: ignore[assignment,method-assign]
    service._latest_budget_ts = _latest  # type: ignore[assignment,method-assign]
    service._latest_personnel_ts = _latest  # type: ignore[assignment,method-assign]
    service._latest_shared_ts = _latest  # type: ignore[assignment,method-assign]


@pytest.mark.asyncio
async def test_delta_pct_one_decimal_round_half_up(stub_session: StubSession) -> None:
    """CR-013 — delta_pct is quantized to one decimal with ROUND_HALF_UP."""
    cycle = make_cycle(state=CycleState.open)
    stub_session.register_cycle(cycle)
    unit = make_org_unit(code="4000", level_code="4000")
    account = make_account(code="51010000")

    service = ConsolidatedReportService(stub_session)  # type: ignore[arg-type]
    _install(
        service,
        units=[unit],
        accounts={account.id: account},
        budget_map={(unit.id, account.id): Decimal("1200")},
        actuals_map={(unit.id, account.id): Decimal("1100")},
    )

    scope = ReportScope(user_id=unit.id, all_scopes=True)
    report = await service.build(cycle_id=cycle.id, scope=scope)

    row = next(r for r in report.rows if r.account_code == "51010000")
    assert row.delta_amount == Decimal("100")
    # (100 / 1100) * 100 = 9.0909... → "9.1"
    assert row.delta_pct == "9.1"


@pytest.mark.asyncio
async def test_delta_pct_na_when_actual_zero(stub_session: StubSession) -> None:
    """CR-014 — actual=0 → delta_pct literal ``'N/A'``."""
    cycle = make_cycle(state=CycleState.open)
    stub_session.register_cycle(cycle)
    unit = make_org_unit(code="4000", level_code="4000")
    account = make_account(code="51010000")

    service = ConsolidatedReportService(stub_session)  # type: ignore[arg-type]
    _install(
        service,
        units=[unit],
        accounts={account.id: account},
        budget_map={(unit.id, account.id): Decimal("100")},
        actuals_map={(unit.id, account.id): Decimal("0")},
    )

    scope = ReportScope(user_id=unit.id, all_scopes=True)
    report = await service.build(cycle_id=cycle.id, scope=scope)

    row = next(r for r in report.rows if r.account_code == "51010000")
    assert row.delta_pct == "N/A"


@pytest.mark.asyncio
async def test_budget_status_not_uploaded_when_no_upload(stub_session: StubSession) -> None:
    """CR-015 — units without an upload still get a row."""
    cycle = make_cycle(state=CycleState.open)
    stub_session.register_cycle(cycle)
    unit = make_org_unit(code="4000", level_code="4000")
    account = make_account(code="51010000")

    service = ConsolidatedReportService(stub_session)  # type: ignore[arg-type]
    _install(
        service,
        units=[unit],
        accounts={account.id: account},
        budget_map={},
        actuals_map={},
    )

    scope = ReportScope(user_id=unit.id, all_scopes=True)
    report = await service.build(cycle_id=cycle.id, scope=scope)

    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.budget_status == "not_uploaded"
    assert row.operational_budget is None


@pytest.mark.asyncio
async def test_personnel_budget_null_for_4000_level(stub_session: StubSession) -> None:
    """CR-016 — rows below level 1000 have null personnel/shared fields."""
    cycle = make_cycle(state=CycleState.open)
    stub_session.register_cycle(cycle)
    unit = make_org_unit(code="4000", level_code="4000")
    account = make_account(code="51010000")

    service = ConsolidatedReportService(stub_session)  # type: ignore[arg-type]
    _install(
        service,
        units=[unit],
        accounts={account.id: account},
        budget_map={(unit.id, account.id): Decimal("100")},
        personnel_map={(unit.id, account.id): Decimal("50")},
        shared_map={(unit.id, account.id): Decimal("25")},
        actuals_map={(unit.id, account.id): Decimal("80")},
    )

    scope = ReportScope(user_id=unit.id, all_scopes=True)
    report = await service.build(cycle_id=cycle.id, scope=scope)

    row = next(r for r in report.rows if r.account_code == "51010000")
    assert row.personnel_budget is None
    assert row.shared_cost is None


@pytest.mark.asyncio
async def test_personnel_budget_populated_for_1000_level(stub_session: StubSession) -> None:
    """CR-016 — level 1000 rows include personnel / shared cost columns."""
    cycle = make_cycle(state=CycleState.open)
    stub_session.register_cycle(cycle)
    unit = make_org_unit(code="1000", level_code="1000")
    account = make_account(code="51010000")

    service = ConsolidatedReportService(stub_session)  # type: ignore[arg-type]
    _install(
        service,
        units=[unit],
        accounts={account.id: account},
        budget_map={(unit.id, account.id): Decimal("1000")},
        personnel_map={(unit.id, account.id): Decimal("500")},
        shared_map={(unit.id, account.id): Decimal("250")},
        actuals_map={(unit.id, account.id): Decimal("800")},
    )

    scope = ReportScope(user_id=unit.id, all_scopes=True)
    report = await service.build(cycle_id=cycle.id, scope=scope)

    row = next(r for r in report.rows if r.account_code == "51010000")
    assert row.personnel_budget == Decimal("500")
    assert row.shared_cost == Decimal("250")
