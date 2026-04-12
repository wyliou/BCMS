"""API-tier smoke tests for :mod:`app.api.v1.shared_costs`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.api.v1.shared_costs import router as sc_router
from app.core.errors import AppError, BatchValidationError
from app.core.security.auth_service import AuthService
from app.core.security.models import User
from app.core.security.roles import Role
from app.domain.shared_costs.models import SharedCostUpload
from app.domain.shared_costs.service import SharedCostImportService
from app.infra.db.session import get_session
from app.main import _app_error_handler, _unhandled_exception_handler
from tests.unit.shared_costs.conftest import FakeSession, make_cycle, make_user


def _now() -> datetime:
    return datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc)


def _make_upload_row(*, cycle_id: Any, version: int = 1) -> SharedCostUpload:
    """Build a minimal SharedCostUpload row for mocks."""
    upload = SharedCostUpload(
        cycle_id=cycle_id,
        uploader_user_id=uuid4(),
        uploaded_at=_now(),
        filename="shared_costs.csv",
        file_hash=b"\x00" * 32,
        version=version,
        affected_org_units_summary={"unit_count": 0, "unit_codes": [], "diff_changed": 0},
    )
    upload.id = uuid4()
    return upload


@pytest.fixture
def sc_app() -> FastAPI:
    """Build a FastAPI app that mounts the shared_costs router."""
    application = FastAPI()
    application.include_router(sc_router, prefix="/api/v1")
    application.add_exception_handler(AppError, _app_error_handler)
    application.add_exception_handler(Exception, _unhandled_exception_handler)

    shared_session = FakeSession()

    async def _override_session() -> AsyncIterator[Any]:
        yield shared_session

    application.dependency_overrides[get_session] = _override_session
    application.state._shared_session = shared_session  # type: ignore[attr-defined]

    patcher = patch(
        "app.api.v1.shared_costs._build_service",
        new=lambda db: SharedCostImportService(db),
    )
    patcher.start()
    application.state._patcher = patcher  # type: ignore[attr-defined]
    return application


@pytest_asyncio.fixture
async def sc_client(
    sc_app: FastAPI,
) -> AsyncIterator[httpx.AsyncClient]:
    """Async HTTP client bound to the shared_costs app."""
    transport = httpx.ASGITransport(app=sc_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    sc_app.state._patcher.stop()  # type: ignore[attr-defined]


def _finance_user() -> User:
    """Return a FinanceAdmin user."""
    return make_user(role=Role.FinanceAdmin, email="finance@example.com")


def _hr_user() -> User:
    """Return an HRAdmin user (not permitted for shared costs)."""
    return User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=b"\x00" * 32,
        name="HR Admin",
        email_enc=b"hr@example.com",
        email_hash=b"\x00" * 32,
        roles=[Role.HRAdmin.value],
        org_unit_id=None,
        is_active=True,
    )


# ------------------------------------------------------------ auth helper


def _patch_auth(monkeypatch: pytest.MonkeyPatch, user: User) -> None:
    """Make AuthService.current_user return ``user`` unconditionally."""

    async def _fake_current_user(self: AuthService, request: object) -> User:
        del self, request
        return user

    monkeypatch.setattr(AuthService, "current_user", _fake_current_user)


# ============================================================
#          test_import_requires_finance_admin
# ============================================================


async def test_import_requires_finance_admin(
    sc_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST as HRAdmin is rejected with 403 RBAC_001."""
    _patch_auth(monkeypatch, _hr_user())
    cycle_id = uuid4()
    response = await sc_client.post(
        f"/api/v1/cycles/{cycle_id}/shared-cost-imports",
        files={"file": ("sc.csv", b"dept_id,account_code,amount\n4023,SC001,1000", "text/csv")},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "RBAC_001"


# ============================================================
#          test_import_valid_csv_returns_201
# ============================================================


async def test_import_valid_csv_returns_201(
    sc_client: httpx.AsyncClient,
    sc_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST valid CSV as FinanceAdmin returns 201 with the upload payload."""
    _patch_auth(monkeypatch, _finance_user())

    cycle = make_cycle()
    session: FakeSession = sc_app.state._shared_session  # type: ignore[attr-defined]
    session.cycles[cycle.id] = cycle

    async def _fake_import_(
        self: SharedCostImportService,
        *,
        cycle_id: Any,
        filename: str,
        content: bytes,
        user: User,
    ) -> SharedCostUpload:
        del self, filename, content, user
        return _make_upload_row(cycle_id=cycle_id, version=1)

    monkeypatch.setattr(SharedCostImportService, "import_", _fake_import_)

    response = await sc_client.post(
        f"/api/v1/cycles/{cycle.id}/shared-cost-imports",
        files={"file": ("sc.csv", b"dept_id,account_code,amount\n4023,SC001,1000", "text/csv")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 1
    assert body["cycle_id"] == str(cycle.id)


# ============================================================
#          test_import_invalid_rows_returns_400
# ============================================================


async def test_import_invalid_rows_returns_400(
    sc_client: httpx.AsyncClient,
    sc_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST bad CSV returns 400 with SHARED_004 envelope."""
    _patch_auth(monkeypatch, _finance_user())

    cycle = make_cycle()
    session: FakeSession = sc_app.state._shared_session  # type: ignore[attr-defined]
    session.cycles[cycle.id] = cycle

    async def _fake_import_(*args: Any, **kwargs: Any) -> SharedCostUpload:
        del args, kwargs
        raise BatchValidationError(
            "SHARED_004",
            errors=[
                {
                    "row": 2,
                    "column": "dept_id",
                    "code": "SHARED_001",
                    "reason": "Unknown dept_id: 'XXXX'",
                }
            ],
        )

    monkeypatch.setattr(SharedCostImportService, "import_", _fake_import_)

    response = await sc_client.post(
        f"/api/v1/cycles/{cycle.id}/shared-cost-imports",
        files={"file": ("bad.csv", b"dept_id,account_code,amount\nXXXX,SC001,1000", "text/csv")},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "SHARED_004"
    assert body["error"]["details"][0]["code"] == "SHARED_001"


# ============================================================
#          test_list_versions_requires_authentication
# ============================================================


async def test_list_versions_requires_authentication(
    sc_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unauthenticated GET /cycles/{id}/shared-cost-imports returns 401."""

    async def _fake_unauth(self: AuthService, request: object) -> User:
        del self, request
        from app.core.errors import UnauthenticatedError

        raise UnauthenticatedError("AUTH_004", "Session expired")

    monkeypatch.setattr(AuthService, "current_user", _fake_unauth)

    response = await sc_client.get(f"/api/v1/cycles/{uuid4()}/shared-cost-imports")
    assert response.status_code == 401
