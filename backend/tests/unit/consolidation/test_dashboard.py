"""Unit tests for :class:`DashboardService` (FR-004, FR-014)."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.errors import InfraError
from app.core.security.roles import Role
from app.domain.consolidation.dashboard import DashboardService
from app.domain.cycles.models import CycleState
from tests.unit.consolidation.conftest import (
    StubSession,
    make_budget_upload,
    make_cycle,
    make_org_unit,
    make_resubmit,
    make_template,
    make_user,
)


def _install_stubs(
    service: DashboardService,
    *,
    units: list[Any] | None = None,
    uploads: dict[Any, Any] | None = None,
    templates: dict[Any, Any] | None = None,
    resubmits: set[Any] | None = None,
    unsubmitted: set[Any] | None = None,
) -> None:
    """Monkeypatch the private fetch helpers on ``service`` with fakes.

    Args:
        service: Target dashboard service instance.
        units: Filing unit list returned by :meth:`_list_filing_units`.
        uploads: Map returned by :meth:`_latest_uploads_by_unit`.
        templates: Map returned by :meth:`_templates_by_unit`.
        resubmits: Set returned by :meth:`_open_resubmit_ids`.
        unsubmitted: Set returned by the ``unsubmitted_for_cycle``
            helper used inside :meth:`_collect_rows` — patched on the
            dashboard module.
    """

    async def _units(*, scope: Any) -> list[Any]:
        return list(units or [])

    async def _uploads(*, cycle_id: Any) -> dict[Any, Any]:
        return dict(uploads or {})

    async def _templates(*, cycle_id: Any) -> dict[Any, Any]:
        return dict(templates or {})

    async def _resubmits(*, cycle_id: Any) -> set[Any]:
        return set(resubmits or set())

    service._list_filing_units = _units  # type: ignore[assignment,method-assign]
    service._latest_uploads_by_unit = _uploads  # type: ignore[assignment,method-assign]
    service._templates_by_unit = _templates  # type: ignore[assignment,method-assign]
    service._open_resubmit_ids = _resubmits  # type: ignore[assignment,method-assign]

    if unsubmitted is not None:
        import app.domain.consolidation.dashboard as dashboard_module

        async def _unsub(_db: Any, _cycle_id: Any) -> list[Any]:
            return list(unsubmitted)

        dashboard_module.unsubmitted_for_cycle = _unsub  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_empty_cycle_returns_sentinel(stub_session: StubSession) -> None:
    """Draft cycle returns the 尚未開放週期 sentinel (FR-004)."""
    cycle = make_cycle(state=CycleState.draft)
    stub_session.register_cycle(cycle)
    service = DashboardService(stub_session)  # type: ignore[arg-type]
    user = make_user(role=Role.SystemAdmin)

    response = await service.status_for_user(cycle_id=cycle.id, user=user)

    assert response.sentinel == "尚未開放週期"
    assert response.items == []


@pytest.mark.asyncio
async def test_status_uploaded_when_upload_exists(stub_session: StubSession) -> None:
    """An existing :class:`BudgetUpload` flips the row to ``uploaded``."""
    cycle = make_cycle(state=CycleState.open)
    stub_session.register_cycle(cycle)
    unit = make_org_unit(code="4001")
    upload = make_budget_upload(cycle_id=cycle.id, org_unit_id=unit.id, version=2)
    template = make_template(cycle_id=cycle.id, org_unit_id=unit.id, download_count=3)

    service = DashboardService(stub_session)  # type: ignore[arg-type]
    _install_stubs(
        service,
        units=[unit],
        uploads={unit.id: upload},
        templates={unit.id: template},
        resubmits=set(),
        unsubmitted=set(),
    )

    user = make_user(role=Role.SystemAdmin)
    response = await service.status_for_user(cycle_id=cycle.id, user=user)

    assert len(response.items) == 1
    row = response.items[0]
    assert row.status == "uploaded"
    assert row.version == 2
    assert row.last_uploaded_at is not None


@pytest.mark.asyncio
async def test_status_not_downloaded_when_no_download(stub_session: StubSession) -> None:
    """A template with ``download_count=0`` yields ``not_downloaded``."""
    cycle = make_cycle(state=CycleState.open)
    stub_session.register_cycle(cycle)
    unit = make_org_unit(code="4002")
    template = make_template(cycle_id=cycle.id, org_unit_id=unit.id, download_count=0)

    service = DashboardService(stub_session)  # type: ignore[arg-type]
    _install_stubs(
        service,
        units=[unit],
        uploads={},
        templates={unit.id: template},
        resubmits=set(),
        unsubmitted={unit.id},
    )

    user = make_user(role=Role.SystemAdmin)
    response = await service.status_for_user(cycle_id=cycle.id, user=user)

    assert response.items[0].status == "not_downloaded"


@pytest.mark.asyncio
async def test_status_resubmit_requested_wins(stub_session: StubSession) -> None:
    """An open :class:`ResubmitRequest` pins the status."""
    cycle = make_cycle(state=CycleState.open)
    stub_session.register_cycle(cycle)
    unit = make_org_unit(code="4003")
    resubmit = make_resubmit(cycle_id=cycle.id, org_unit_id=unit.id)

    service = DashboardService(stub_session)  # type: ignore[arg-type]
    _install_stubs(
        service,
        units=[unit],
        uploads={},
        templates={},
        resubmits={resubmit.org_unit_id},
        unsubmitted={unit.id},
    )

    user = make_user(role=Role.SystemAdmin)
    response = await service.status_for_user(cycle_id=cycle.id, user=user)

    assert response.items[0].status == "resubmit_requested"


@pytest.mark.asyncio
async def test_company_reviewer_gets_summary_only(stub_session: StubSession) -> None:
    """CompanyReviewer receives ``items=[]`` + a populated ``summary``."""
    cycle = make_cycle(state=CycleState.open)
    stub_session.register_cycle(cycle)
    unit_a = make_org_unit(code="4100")
    unit_b = make_org_unit(code="4200")
    upload = make_budget_upload(cycle_id=cycle.id, org_unit_id=unit_a.id)

    service = DashboardService(stub_session)  # type: ignore[arg-type]
    _install_stubs(
        service,
        units=[unit_a, unit_b],
        uploads={unit_a.id: upload},
    )

    user = make_user(role=Role.CompanyReviewer)
    response = await service.status_for_user(cycle_id=cycle.id, user=user)

    assert response.items == []
    assert response.summary is not None
    assert response.summary["total_units"] == 2
    assert response.summary["uploaded"] == 1
    assert response.summary["pending"] == 1


@pytest.mark.asyncio
async def test_stale_fallback_on_infra_error(stub_session: StubSession) -> None:
    """An :class:`InfraError` during collection triggers the stale fallback."""
    cycle = make_cycle(state=CycleState.open)
    stub_session.register_cycle(cycle)
    service = DashboardService(stub_session)  # type: ignore[arg-type]

    async def _boom(**_kwargs: Any) -> list[Any]:
        raise InfraError("SYS_001", "db down")

    service._collect_rows = _boom  # type: ignore[assignment,method-assign]

    user = make_user(role=Role.SystemAdmin)
    response = await service.status_for_user(cycle_id=cycle.id, user=user)

    assert response.stale is True
    assert response.items == []
