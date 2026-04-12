"""API-tier smoke test for the open-cycle orchestrator endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.api.v1.orchestrators.open_cycle import (
    CycleSnapshot,
    DispatchSummary,
    GenerationSummary,
    OpenCycleResponse,
)
from app.api.v1.orchestrators.open_cycle import router as open_cycle_router
from app.core.errors import AppError
from app.infra.db.session import get_session
from app.main import _app_error_handler, _unhandled_exception_handler


@pytest.fixture
def open_cycle_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Build a FastAPI app wired to a stubbed ``open_cycle`` orchestrator."""
    application = FastAPI()
    application.include_router(open_cycle_router, prefix="/api/v1")
    application.add_exception_handler(AppError, _app_error_handler)
    application.add_exception_handler(Exception, _unhandled_exception_handler)

    async def _override_session() -> AsyncIterator[Any]:
        yield object()

    application.dependency_overrides[get_session] = _override_session

    fixed_response = OpenCycleResponse(
        cycle=CycleSnapshot(
            id=uuid4(),
            fiscal_year=2026,
            status="open",
            reporting_currency="TWD",
        ),
        transition="draft_to_open",
        generation_summary=GenerationSummary(
            total=3,
            generated=3,
            errors=0,
            error_details=[],
        ),
        dispatch_summary=DispatchSummary(
            total_recipients=3,
            sent=3,
            errors=0,
        ),
    )

    async def _fake_open_cycle(**_kwargs: Any) -> OpenCycleResponse:
        return fixed_response

    # Patch the orchestrator function at its import site on the router module.
    import app.api.v1.orchestrators.open_cycle as oc_module

    monkeypatch.setattr(oc_module, "open_cycle", _fake_open_cycle)
    return application


@pytest_asyncio.fixture
async def open_cycle_client(
    open_cycle_app: FastAPI,
) -> AsyncIterator[httpx.AsyncClient]:
    """Async HTTP client bound to the open-cycle app."""
    transport = httpx.ASGITransport(app=open_cycle_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_post_open_cycle_returns_summary(
    open_cycle_client: httpx.AsyncClient,
) -> None:
    """POST /cycles/{id}/open returns the aggregated summary."""
    response = await open_cycle_client.post(f"/api/v1/cycles/{uuid4()}/open")
    assert response.status_code == 200
    body = response.json()
    assert body["transition"] == "draft_to_open"
    assert body["generation_summary"]["generated"] == 3
    assert body["dispatch_summary"]["sent"] == 3
