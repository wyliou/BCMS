"""API-tier smoke tests for :mod:`app.api.v1.personnel`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.api.v1.personnel import router as personnel_router
from app.core.errors import AppError, BatchValidationError
from app.core.security.auth_service import AuthService
from app.core.security.models import User
from app.core.security.roles import Role
from app.domain.personnel.models import PersonnelBudgetUpload
from app.domain.personnel.service import PersonnelImportService
from app.infra.db.session import get_session
from app.main import _app_error_handler, _unhandled_exception_handler
from tests.unit.personnel.conftest import (
    FakeSession,
    make_cycle,
    make_org_unit,
)


def _now_ts() -> str:
    """Return a fixed ISO-8601 timestamp for tests."""
    from datetime import datetime, timezone

    return datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc).isoformat()


@pytest.fixture
def personnel_app() -> FastAPI:
    """Build a FastAPI app that mounts the personnel router."""
    application = FastAPI()
    application.include_router(personnel_router, prefix="/api/v1")
    application.add_exception_handler(AppError, _app_error_handler)
    application.add_exception_handler(Exception, _unhandled_exception_handler)

    shared_session = FakeSession()

    async def _override_session() -> AsyncIterator[Any]:
        yield shared_session

    application.dependency_overrides[get_session] = _override_session
    application.state._shared_session = shared_session  # type: ignore[attr-defined]

    def _patched_builder(db: Any) -> PersonnelImportService:
        return PersonnelImportService(db)

    patcher = patch("app.api.v1.personnel._build_service", new=_patched_builder)
    patcher.start()
    application.state._patcher = patcher  # type: ignore[attr-defined]
    return application


@pytest_asyncio.fixture
async def personnel_client(
    personnel_app: FastAPI,
) -> AsyncIterator[httpx.AsyncClient]:
    """Async HTTP client bound to the personnel app."""
    transport = httpx.ASGITransport(app=personnel_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    personnel_app.state._patcher.stop()  # type: ignore[attr-defined]


def _seed_app(app: FastAPI) -> tuple[Any, Any]:
    """Populate the fake session with one cycle + one filing unit."""
    session: FakeSession = app.state._shared_session  # type: ignore[attr-defined]
    cycle = make_cycle()
    session.cycles[cycle.id] = cycle
    unit = make_org_unit(code="4023")
    session.org_units.append(unit)
    return cycle, unit


def _make_upload(cycle_id: Any) -> PersonnelBudgetUpload:
    """Build a minimal :class:`PersonnelBudgetUpload` for testing."""
    from datetime import datetime, timezone

    row = PersonnelBudgetUpload(
        cycle_id=cycle_id,
        uploader_user_id=uuid4(),
        uploaded_at=datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc),
        filename="personnel.csv",
        file_hash="abc123",
        version=1,
        affected_org_units_summary={"unit_count": 1, "unit_codes": []},
    )
    row.id = uuid4()
    return row


# ============================================================ POST /cycles/{id}/personnel-imports
async def test_import_valid_csv_returns_201(
    personnel_client: httpx.AsyncClient,
    personnel_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid POST returns 201 with the serialized PersonnelBudgetUpload."""
    cycle, unit = _seed_app(personnel_app)

    async def _fake_import(
        self: PersonnelImportService,
        *,
        cycle_id: Any,
        filename: str,
        content: bytes,
        user: User,
    ) -> PersonnelBudgetUpload:
        return _make_upload(cycle_id)

    monkeypatch.setattr(PersonnelImportService, "import_", _fake_import)

    response = await personnel_client.post(
        f"/api/v1/cycles/{cycle.id}/personnel-imports",
        files={
            "file": (
                "personnel.csv",
                b"dept_id,account_code,amount\n4023,HR001,1000",
                "text/csv",
            )
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 1
    assert body["filename"] == "personnel.csv"
    assert body["file_hash"] == "abc123"


async def test_import_requires_hr_admin(
    personnel_client: httpx.AsyncClient,
    personnel_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST as FilingUnitManager returns 403 RBAC_001."""
    cycle, unit = _seed_app(personnel_app)

    filing_user = User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=b"\x00" * 32,
        name="Filer",
        email_enc=b"filer@example.com",
        email_hash=b"\x00" * 32,
        roles=[Role.FilingUnitManager.value],
        org_unit_id=unit.id,
        is_active=True,
    )

    async def _fake_current_user(self: AuthService, request: object) -> User:
        return filing_user

    monkeypatch.setattr(AuthService, "current_user", _fake_current_user)

    response = await personnel_client.post(
        f"/api/v1/cycles/{cycle.id}/personnel-imports",
        files={"file": ("p.csv", b"x", "text/csv")},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "RBAC_001"


async def test_import_invalid_rows_returns_400(
    personnel_client: httpx.AsyncClient,
    personnel_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST bad CSV → 400 with PERS_004 envelope and row-level details."""
    cycle, unit = _seed_app(personnel_app)

    async def _fake_import(*args: Any, **kwargs: Any) -> PersonnelBudgetUpload:
        raise BatchValidationError(
            "PERS_004",
            errors=[
                {
                    "row": 1,
                    "column": "dept_id",
                    "code": "PERS_001",
                    "reason": "Unknown dept_id: 'UNKNOWN'",
                }
            ],
        )

    monkeypatch.setattr(PersonnelImportService, "import_", _fake_import)

    response = await personnel_client.post(
        f"/api/v1/cycles/{cycle.id}/personnel-imports",
        files={"file": ("bad.csv", b"bad content", "text/csv")},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "PERS_004"
    assert body["error"]["details"][0]["row"] == 1
    assert body["error"]["details"][0]["code"] == "PERS_001"


# ============================================================ GET /cycles/{id}/personnel-imports
async def test_list_versions_requires_authentication(
    personnel_client: httpx.AsyncClient,
    personnel_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unauthenticated GET returns 401."""
    cycle, unit = _seed_app(personnel_app)

    async def _raise_auth(self: AuthService, request: object) -> User:
        from app.core.errors import UnauthenticatedError

        raise UnauthenticatedError("AUTH_004", "No session")

    monkeypatch.setattr(AuthService, "current_user", _raise_auth)

    response = await personnel_client.get(f"/api/v1/cycles/{cycle.id}/personnel-imports")
    assert response.status_code == 401


async def test_list_versions_returns_payloads(
    personnel_client: httpx.AsyncClient,
    personnel_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET returns a list of versions ordered by version ascending."""
    cycle, unit = _seed_app(personnel_app)

    async def _fake_list(
        self: PersonnelImportService,
        cycle_id: Any,
    ) -> list[PersonnelBudgetUpload]:
        return [_make_upload(cycle_id), _make_upload(cycle_id)]

    monkeypatch.setattr(PersonnelImportService, "list_versions", _fake_list)

    response = await personnel_client.get(f"/api/v1/cycles/{cycle.id}/personnel-imports")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2


# ============================================================ GET /personnel-imports/{id}
async def test_get_detail_returns_upload(
    personnel_client: httpx.AsyncClient,
    personnel_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /personnel-imports/{id} returns the matching upload row."""
    cycle, unit = _seed_app(personnel_app)
    upload_row = _make_upload(cycle.id)

    async def _fake_get(self: PersonnelImportService, upload_id: Any) -> PersonnelBudgetUpload:
        return upload_row

    monkeypatch.setattr(PersonnelImportService, "get", _fake_get)

    response = await personnel_client.get(f"/api/v1/personnel-imports/{upload_row.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(upload_row.id)
    assert body["version"] == 1
