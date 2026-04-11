"""API-tier smoke tests for :mod:`app.api.v1.accounts`.

Wires the accounts router against a FastAPI app with an in-memory fake
session, patches :func:`_build_service` to inject a pre-seeded
:class:`AccountService`, and exercises each endpoint. The autouse
fixtures in ``tests/api/conftest.py`` provide the SystemAdmin session
cookie and the no-op :class:`AuditService` substitute.
"""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.accounts import cycles_router
from app.api.v1.accounts import router as accounts_router
from app.core.errors import AppError
from app.domain.accounts.models import AccountCategory
from app.infra.db.session import get_session
from app.main import _app_error_handler, _unhandled_exception_handler


@pytest.fixture
def accounts_app() -> FastAPI:
    """Return a FastAPI app mounting the accounts + cycles routers.

    Uses an in-memory fake session via dependency override; every
    request constructs a fresh :class:`AccountService` bound to a
    shared :class:`FakeSession` instance.
    """
    from tests.unit.accounts.conftest import FakeSession, _FakeAudit, make_account_code

    application = FastAPI()
    application.include_router(accounts_router, prefix="/api/v1")
    application.include_router(cycles_router, prefix="/api/v1")
    application.add_exception_handler(AppError, _app_error_handler)
    application.add_exception_handler(Exception, _unhandled_exception_handler)

    shared_session = FakeSession()
    # Pre-seed a couple of accounts so GET /accounts + POST actuals have
    # something to query.
    shared_session.account_codes = [
        make_account_code(code="5101", category=AccountCategory.operational),
        make_account_code(code="5102", category=AccountCategory.operational),
    ]

    async def _override_session() -> AsyncIterator[Any]:
        yield shared_session

    application.dependency_overrides[get_session] = _override_session
    application.state._shared_session = shared_session  # type: ignore[attr-defined]

    # Patch the build helper so the service is wired to the fake audit.
    from unittest.mock import patch

    from app.domain.accounts.service import AccountService

    fake_audit = _FakeAudit()

    def _patched_builder(db: Any) -> AccountService:
        service = AccountService(db)
        service._audit = fake_audit  # type: ignore[assignment]
        return service

    patcher = patch(
        "app.api.v1.accounts._build_service",
        new=_patched_builder,
    )
    patcher.start()
    application.state._patcher = patcher  # type: ignore[attr-defined]
    application.state._fake_audit = fake_audit  # type: ignore[attr-defined]
    return application


@pytest.fixture
async def client(accounts_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Yield an :class:`httpx.AsyncClient` wired to the test app."""
    transport = httpx.ASGITransport(app=accounts_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    accounts_app.state._patcher.stop()  # type: ignore[attr-defined]


# ------------------------------------------------------------------- tests
async def test_list_accounts_smoke(client: httpx.AsyncClient) -> None:
    """``GET /accounts`` returns the seeded rows."""
    response = await client.get("/api/v1/accounts")
    assert response.status_code == 200, response.text
    body = response.json()
    codes = {item["code"] for item in body}
    assert codes == {"5101", "5102"}


async def test_get_account_by_code(client: httpx.AsyncClient) -> None:
    """``GET /accounts/5101`` returns the matching row."""
    response = await client.get("/api/v1/accounts/5101")
    assert response.status_code == 200, response.text
    assert response.json()["code"] == "5101"


async def test_get_account_not_found_returns_envelope(
    client: httpx.AsyncClient,
) -> None:
    """Missing code returns a 404 error envelope with ACCOUNT_001."""
    response = await client.get("/api/v1/accounts/missing")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "ACCOUNT_001"


async def test_upsert_account_persists_via_service(
    client: httpx.AsyncClient,
    accounts_app: FastAPI,
) -> None:
    """``POST /accounts`` with a new code inserts via the service."""
    payload = {
        "code": "7001",
        "name": "Travel",
        "category": "operational",
        "level": 1,
    }
    response = await client.post("/api/v1/accounts", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"] == "7001"
    shared = accounts_app.state._shared_session  # type: ignore[attr-defined]
    assert any(r.code == "7001" for r in shared.account_codes)


async def test_import_actuals_valid_csv(
    client: httpx.AsyncClient,
    accounts_app: FastAPI,
) -> None:
    """``POST /cycles/{id}/actuals`` accepts a valid CSV upload."""
    from tests.unit.accounts.conftest import _FakeOrgUnit

    shared = accounts_app.state._shared_session  # type: ignore[attr-defined]
    shared.org_units = [_FakeOrgUnit("4000"), _FakeOrgUnit("4023")]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["org_unit_code", "account_code", "amount"])
    writer.writeheader()
    writer.writerow({"org_unit_code": "4000", "account_code": "5101", "amount": "100"})
    writer.writerow({"org_unit_code": "4023", "account_code": "5102", "amount": "200"})
    content = buf.getvalue().encode("utf-8")

    cycle_id = uuid4()
    files = {"file": ("actuals.csv", content, "text/csv")}
    response = await client.post(
        f"/api/v1/cycles/{cycle_id}/actuals",
        files=files,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows_imported"] == 2
    assert sorted(body["org_units_affected"]) == ["4000", "4023"]


async def test_import_actuals_invalid_returns_account_002(
    client: httpx.AsyncClient,
    accounts_app: FastAPI,
) -> None:
    """A row error produces a 400 envelope with ACCOUNT_002."""
    from tests.unit.accounts.conftest import _FakeOrgUnit

    shared = accounts_app.state._shared_session  # type: ignore[attr-defined]
    shared.org_units = [_FakeOrgUnit("4000")]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["org_unit_code", "account_code", "amount"])
    writer.writeheader()
    writer.writerow({"org_unit_code": "9999", "account_code": "5101", "amount": "100"})
    content = buf.getvalue().encode("utf-8")

    cycle_id = uuid4()
    files = {"file": ("actuals.csv", content, "text/csv")}
    response = await client.post(
        f"/api/v1/cycles/{cycle_id}/actuals",
        files=files,
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "ACCOUNT_002"
    assert isinstance(body["error"]["details"], list)
    assert len(body["error"]["details"]) >= 1
