"""API-tier smoke tests for :mod:`app.api.v1.dashboard`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.api.v1.dashboard import router as dashboard_router
from app.core.errors import AppError
from app.domain.consolidation.dashboard import DashboardResponse
from app.infra.db.session import get_session
from app.main import _app_error_handler, _unhandled_exception_handler


class _StubDashboardService:
    """Stub service returning a fixed :class:`DashboardResponse`."""

    def __init__(self, response: DashboardResponse) -> None:
        """Initialize with the fixed payload."""
        self._response = response
        self.calls: list[Any] = []

    async def status_for_user(self, **kwargs: Any) -> DashboardResponse:
        """Return the fixed payload and capture the kwargs."""
        self.calls.append(kwargs)
        return self._response


@pytest.fixture
def dashboard_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Build a FastAPI app wired to a stubbed dashboard service."""
    application = FastAPI()
    application.include_router(dashboard_router, prefix="/api/v1")
    application.add_exception_handler(AppError, _app_error_handler)
    application.add_exception_handler(Exception, _unhandled_exception_handler)

    async def _override_session() -> AsyncIterator[Any]:
        yield object()

    application.dependency_overrides[get_session] = _override_session

    stub = _StubDashboardService(DashboardResponse(sentinel="尚未開放週期", items=[]))
    patcher = patch(
        "app.api.v1.dashboard._build_service",
        new=lambda _db: stub,
    )
    patcher.start()
    application.state._patcher = patcher  # type: ignore[attr-defined]
    application.state._stub = stub  # type: ignore[attr-defined]
    return application


@pytest_asyncio.fixture
async def dashboard_client(dashboard_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Async HTTP client bound to the dashboard app."""
    transport = httpx.ASGITransport(app=dashboard_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    dashboard_app.state._patcher.stop()  # type: ignore[attr-defined]


async def test_get_dashboard_returns_sentinel(
    dashboard_client: httpx.AsyncClient,
) -> None:
    """GET /cycles/{id}/dashboard smoke test."""
    response = await dashboard_client.get(f"/api/v1/cycles/{uuid4()}/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["sentinel"] == "尚未開放週期"
