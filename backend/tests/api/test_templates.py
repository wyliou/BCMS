"""API-tier smoke tests for :mod:`app.api.v1.templates`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.api.v1.templates import router as templates_router
from app.core.errors import AppError
from app.core.security.auth_service import AuthService
from app.core.security.models import User
from app.core.security.roles import Role
from app.domain.templates.service import TemplateGenerationResult, TemplateService
from app.infra.db.session import get_session
from app.main import _app_error_handler, _unhandled_exception_handler
from tests.unit.templates.conftest import (
    FakeAudit,
    FakeSession,
    make_account,
    make_cycle,
    make_org_unit,
)


@pytest.fixture
def templates_app() -> FastAPI:
    """Build a FastAPI app that mounts the templates router on a fake session."""
    application = FastAPI()
    application.include_router(templates_router, prefix="/api/v1")
    application.add_exception_handler(AppError, _app_error_handler)
    application.add_exception_handler(Exception, _unhandled_exception_handler)

    shared_session = FakeSession()

    async def _override_session() -> AsyncIterator[Any]:
        yield shared_session

    application.dependency_overrides[get_session] = _override_session
    application.state._shared_session = shared_session  # type: ignore[attr-defined]

    def _patched_builder(db: Any) -> TemplateService:
        service = TemplateService(db)
        service._audit = FakeAudit()  # type: ignore[assignment]
        return service

    patcher = patch("app.api.v1.templates._build_service", new=_patched_builder)
    patcher.start()
    application.state._patcher = patcher  # type: ignore[attr-defined]
    return application


@pytest_asyncio.fixture
async def templates_client(
    templates_app: FastAPI,
) -> AsyncIterator[httpx.AsyncClient]:
    """Async HTTP client bound to the templates app."""
    transport = httpx.ASGITransport(app=templates_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    templates_app.state._patcher.stop()  # type: ignore[attr-defined]


def _seed_generated(session: FakeSession) -> tuple[Any, Any]:
    """Populate the fake session with a ready-to-download template row."""
    cycle = make_cycle()
    session.cycles[cycle.id] = cycle
    unit = make_org_unit(code="4023")
    session.org_units.append(unit)
    session.account_codes.append(make_account(code="5101"))
    return cycle, unit


async def test_regenerate_returns_result(
    templates_client: httpx.AsyncClient,
    templates_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST regenerate returns a JSON TemplateGenerationResult."""
    session: FakeSession = templates_app.state._shared_session  # type: ignore[attr-defined]
    cycle, unit = _seed_generated(session)

    # Stub the service's regenerate to bypass storage I/O.
    async def _fake_regenerate(
        self: TemplateService, *, cycle: Any, org_unit: Any, user: User
    ) -> TemplateGenerationResult:
        del self, cycle, user
        return TemplateGenerationResult(
            org_unit_id=org_unit.id,
            status="generated",
            error=None,
            template_id=uuid4(),
        )

    monkeypatch.setattr(TemplateService, "regenerate", _fake_regenerate)

    response = await templates_client.post(
        f"/api/v1/cycles/{cycle.id}/templates/{unit.id}/regenerate"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "generated"
    assert body["org_unit_id"] == str(unit.id)


async def test_regenerate_missing_cycle_returns_tpl_002(
    templates_client: httpx.AsyncClient,
    templates_app: FastAPI,
) -> None:
    """Missing cycle id → 404 TPL_002."""
    del templates_app
    response = await templates_client.post(
        f"/api/v1/cycles/{uuid4()}/templates/{uuid4()}/regenerate"
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "TPL_002"


async def test_download_returns_xlsx(
    templates_client: httpx.AsyncClient,
    templates_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET download returns application/vnd...spreadsheetml bytes."""
    session: FakeSession = templates_app.state._shared_session  # type: ignore[attr-defined]
    cycle, unit = _seed_generated(session)

    async def _fake_download(
        self: TemplateService, *, cycle_id: Any, org_unit_id: Any, user: User
    ) -> tuple[str, bytes]:
        del self, cycle_id, org_unit_id, user
        return f"{unit.code}_{cycle.fiscal_year}_budget_template.xlsx", b"fake-bytes"

    monkeypatch.setattr(TemplateService, "download", _fake_download)

    response = await templates_client.get(f"/api/v1/cycles/{cycle.id}/templates/{unit.id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in response.headers["content-disposition"]
    assert response.content == b"fake-bytes"


async def test_regenerate_requires_finance_admin(
    templates_client: httpx.AsyncClient,
    templates_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST regenerate as a FilingUnitManager returns 403 RBAC_001."""
    session: FakeSession = templates_app.state._shared_session  # type: ignore[attr-defined]
    cycle, unit = _seed_generated(session)

    filing_user = User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=b"\x00" * 32,
        name="Filer",
        email_enc=b"",
        email_hash=b"\x00" * 32,
        roles=[Role.FilingUnitManager.value],
        org_unit_id=unit.id,
        is_active=True,
    )

    async def _fake_current_user(self: AuthService, request: object) -> User:
        del self, request
        return filing_user

    monkeypatch.setattr(AuthService, "current_user", _fake_current_user)

    response = await templates_client.post(
        f"/api/v1/cycles/{cycle.id}/templates/{unit.id}/regenerate"
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "RBAC_001"
