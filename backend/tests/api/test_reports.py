"""API-tier smoke tests for :mod:`app.api.v1.reports`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.api.v1.reports import router as reports_router
from app.core.errors import AppError
from app.domain.consolidation.export import ExportEnqueueResult
from app.domain.consolidation.report import ConsolidatedReport, ReportScope
from app.infra.db.session import get_session
from app.main import _app_error_handler, _unhandled_exception_handler


class _StubReportService:
    """Stub :class:`ConsolidatedReportService` returning a fixed report."""

    def __init__(self, report: ConsolidatedReport) -> None:
        """Initialize with the fixed report payload."""
        self._report = report

    async def resolve_scope(self, *, user: Any) -> ReportScope:
        """Return a narrow test scope."""
        return ReportScope(user_id=user.id, all_scopes=False)

    async def build(self, **_kwargs: Any) -> ConsolidatedReport:
        """Return the fixed report."""
        return self._report


class _StubExportService:
    """Stub :class:`ReportExportService` returning a fixed enqueue result."""

    def __init__(self, result: ExportEnqueueResult) -> None:
        """Initialize with the fixed result."""
        self._result = result

    async def export_async(self, **_kwargs: Any) -> ExportEnqueueResult:
        """Return the fixed result."""
        return self._result


@pytest.fixture
def reports_app() -> FastAPI:
    """Build a FastAPI app with stubbed report + export services."""
    application = FastAPI()
    application.include_router(reports_router, prefix="/api/v1")
    application.add_exception_handler(AppError, _app_error_handler)
    application.add_exception_handler(Exception, _unhandled_exception_handler)

    async def _override_session() -> AsyncIterator[Any]:
        yield object()

    application.dependency_overrides[get_session] = _override_session

    fixed_report = ConsolidatedReport(cycle_id=uuid4(), rows=[])
    fixed_result = ExportEnqueueResult(
        mode="sync",
        file_url="exports/test/key.xlsx",
    )
    stub_rpt = _StubReportService(fixed_report)
    stub_exp = _StubExportService(fixed_result)

    patcher_rpt = patch(
        "app.api.v1.reports._build_report_service",
        new=lambda _db: stub_rpt,
    )
    patcher_exp = patch(
        "app.api.v1.reports._build_export_service",
        new=lambda _db: stub_exp,
    )
    patcher_rpt.start()
    patcher_exp.start()
    application.state._patchers = (patcher_rpt, patcher_exp)  # type: ignore[attr-defined]
    return application


@pytest_asyncio.fixture
async def reports_client(reports_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Async HTTP client bound to the reports app."""
    transport = httpx.ASGITransport(app=reports_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    for patcher in reports_app.state._patchers:  # type: ignore[attr-defined]
        patcher.stop()


async def test_get_consolidated_report(reports_client: httpx.AsyncClient) -> None:
    """GET /cycles/{id}/reports/consolidated smoke test."""
    response = await reports_client.get(f"/api/v1/cycles/{uuid4()}/reports/consolidated")
    assert response.status_code == 200
    assert "rows" in response.json()


async def test_post_export_sync_returns_201(
    reports_client: httpx.AsyncClient,
) -> None:
    """POST /cycles/{id}/reports/exports returns 201 for sync path."""
    response = await reports_client.post(f"/api/v1/cycles/{uuid4()}/reports/exports?format=xlsx")
    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "sync"
    assert body["file_url"] == "exports/test/key.xlsx"
