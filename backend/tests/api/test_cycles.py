"""API-tier smoke tests for :mod:`app.api.v1.cycles`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.api.v1.cycles import router as cycles_router
from app.api.v1.orchestrators.open_cycle import router as open_cycle_router
from app.core.errors import AppError
from app.core.security.roles import Role
from app.domain.cycles.models import CycleState
from app.domain.cycles.service import CycleService
from app.infra.db.session import get_session
from app.main import _app_error_handler, _unhandled_exception_handler
from tests.unit.cycles.conftest import (
    FakeAudit,
    FakeSession,
    make_cycle,
    make_org_unit,
    make_user,
)


@pytest.fixture
def cycles_app() -> FastAPI:
    """Build a FastAPI app that mounts the cycles router on a fake session."""
    application = FastAPI()
    application.include_router(cycles_router, prefix="/api/v1")
    application.include_router(open_cycle_router, prefix="/api/v1")
    application.add_exception_handler(AppError, _app_error_handler)
    application.add_exception_handler(Exception, _unhandled_exception_handler)

    shared_session = FakeSession()

    async def _override_session() -> AsyncIterator[Any]:
        yield shared_session

    application.dependency_overrides[get_session] = _override_session
    application.state._shared_session = shared_session  # type: ignore[attr-defined]

    def _patched_builder(db: Any) -> CycleService:
        service = CycleService(db)
        service._audit = FakeAudit()  # type: ignore[assignment]
        return service

    patcher = patch("app.api.v1.cycles._build_service", new=_patched_builder)
    patcher.start()
    application.state._patcher = patcher  # type: ignore[attr-defined]
    return application


@pytest_asyncio.fixture
async def cycles_client(cycles_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Async HTTP client bound to the cycles app."""
    transport = httpx.ASGITransport(app=cycles_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    cycles_app.state._patcher.stop()  # type: ignore[attr-defined]


async def test_post_cycles_creates_draft(cycles_client: httpx.AsyncClient) -> None:
    """POST /cycles returns 201 with a Draft row."""
    response = await cycles_client.post(
        "/api/v1/cycles",
        json={
            "fiscal_year": 2026,
            "deadline": "2026-12-31",
            "reporting_currency": "TWD",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["fiscal_year"] == 2026
    assert body["status"] == "draft"


async def test_get_cycles_returns_seeded_rows(
    cycles_client: httpx.AsyncClient, cycles_app: FastAPI
) -> None:
    """GET /cycles returns the seeded fake session rows."""
    session = cycles_app.state._shared_session  # type: ignore[attr-defined]
    session.cycles.append(make_cycle(fiscal_year=2025, status=CycleState.closed))
    session.cycles.append(make_cycle(fiscal_year=2026, status=CycleState.open))
    response = await cycles_client.get("/api/v1/cycles")
    assert response.status_code == 200
    body = response.json()
    years = {row["fiscal_year"] for row in body}
    assert years == {2025, 2026}


async def test_open_cycle_returns_orchestrator_summary(
    cycles_client: httpx.AsyncClient, cycles_app: FastAPI
) -> None:
    """POST /cycles/{id}/open runs the Batch 6 orchestrator and returns its summary."""
    session: FakeSession = cycles_app.state._shared_session  # type: ignore[attr-defined]
    unit = make_org_unit(code="4000")
    session.org_units = [unit]
    session.users = [make_user(roles=[Role.FilingUnitManager], org_unit_id=unit.id)]
    cycle = make_cycle(status=CycleState.draft)
    session.cycles.append(cycle)

    # Reason: the Batch 6 orchestrator delegates Step 3 (template
    # generation) and Step 4 (notification dispatch) to collaborators
    # that do not understand the minimal FakeSession used here. Patch
    # both through the ``open_cycle`` helper so the transition runs
    # end-to-end without real templates / SMTP.
    import app.api.v1.orchestrators.open_cycle as oc_module
    from app.domain.templates.service import TemplateGenerationResult

    async def _fake_generate(**kwargs: Any) -> list[TemplateGenerationResult]:
        units = kwargs.get("filing_units", [])
        return [TemplateGenerationResult(org_unit_id=u.id, status="generated") for u in units]

    class _FakeTemplateService:
        def __init__(self, _db: Any) -> None:
            pass

        generate_for_cycle = staticmethod(_fake_generate)

    original_ts = oc_module.TemplateService
    oc_module.TemplateService = _FakeTemplateService  # type: ignore[misc]
    try:
        response = await cycles_client.post(f"/api/v1/cycles/{cycle.id}/open")
    finally:
        oc_module.TemplateService = original_ts  # type: ignore[misc]
    assert response.status_code == 200
    body = response.json()
    assert body["transition"] == "draft_to_open"
    assert body["cycle"]["status"] == "open"


async def test_patch_reminder_schedule_empty_disables(
    cycles_client: httpx.AsyncClient, cycles_app: FastAPI
) -> None:
    """PATCH reminders with days_before=[] clears the schedule."""
    session: FakeSession = cycles_app.state._shared_session  # type: ignore[attr-defined]
    cycle = make_cycle(status=CycleState.open)
    session.cycles.append(cycle)
    # Pre-seed a schedule that should be wiped.
    from datetime import datetime, timezone

    from app.domain.cycles.models import CycleReminderSchedule

    pre = CycleReminderSchedule(
        cycle_id=cycle.id,
        days_before=7,
        created_at=datetime.now(tz=timezone.utc),
    )
    pre.id = uuid4()
    session.reminders.append(pre)

    response = await cycles_client.patch(
        f"/api/v1/cycles/{cycle.id}/reminders",
        json={"days_before": []},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == []
    assert [r for r in session.reminders if r.cycle_id == cycle.id] == []


async def test_get_filing_units(cycles_client: httpx.AsyncClient, cycles_app: FastAPI) -> None:
    """GET /cycles/{id}/filing-units returns the enumerated rows."""
    session: FakeSession = cycles_app.state._shared_session  # type: ignore[attr-defined]
    unit = make_org_unit(code="4000")
    session.org_units = [unit]
    cycle = make_cycle(status=CycleState.draft)
    session.cycles.append(cycle)
    response = await cycles_client.get(f"/api/v1/cycles/{cycle.id}/filing-units")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["code"] == "4000"
