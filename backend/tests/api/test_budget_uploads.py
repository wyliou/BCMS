"""API-tier smoke tests for :mod:`app.api.v1.budget_uploads`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.api.v1.budget_uploads import router as budget_router
from app.core.errors import AppError, BatchValidationError
from app.core.security.auth_service import AuthService
from app.core.security.models import User
from app.core.security.roles import Role
from app.domain.budget_uploads.models import BudgetUpload, UploadStatus
from app.domain.budget_uploads.service import BudgetUploadService
from app.infra.db.session import get_session
from app.main import _app_error_handler, _unhandled_exception_handler
from tests.unit.budget_uploads.conftest import (
    FakeSession,
    make_cycle,
    make_org_unit,
)


@pytest.fixture
def budget_app() -> FastAPI:
    """Build a FastAPI app that mounts the budget_uploads router."""
    application = FastAPI()
    application.include_router(budget_router, prefix="/api/v1")
    application.add_exception_handler(AppError, _app_error_handler)
    application.add_exception_handler(Exception, _unhandled_exception_handler)

    shared_session = FakeSession()

    async def _override_session() -> AsyncIterator[Any]:
        yield shared_session

    application.dependency_overrides[get_session] = _override_session
    application.state._shared_session = shared_session  # type: ignore[attr-defined]

    def _patched_builder(db: Any) -> BudgetUploadService:
        return BudgetUploadService(db)

    patcher = patch("app.api.v1.budget_uploads._build_service", new=_patched_builder)
    patcher.start()
    application.state._patcher = patcher  # type: ignore[attr-defined]
    return application


@pytest_asyncio.fixture
async def budget_client(
    budget_app: FastAPI,
) -> AsyncIterator[httpx.AsyncClient]:
    """Async HTTP client bound to the budget uploads app."""
    transport = httpx.ASGITransport(app=budget_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    budget_app.state._patcher.stop()  # type: ignore[attr-defined]


def _seed_app(app: FastAPI) -> tuple[Any, Any]:
    """Populate the fake session with one cycle + one filing unit."""
    session: FakeSession = app.state._shared_session  # type: ignore[attr-defined]
    cycle = make_cycle()
    session.cycles[cycle.id] = cycle
    unit = make_org_unit(code="4023")
    session.org_units.append(unit)
    return cycle, unit


# ---------------------------------------------------- POST /cycles/{id}/uploads/{unit}
async def test_upload_happy_path_returns_201(
    budget_client: httpx.AsyncClient,
    budget_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid POST returns 201 with the serialized BudgetUpload."""
    cycle, unit = _seed_app(budget_app)

    async def _fake_upload(
        self: BudgetUploadService,
        *,
        cycle_id: Any,
        org_unit_id: Any,
        filename: str,
        content: bytes,
        user: User,
    ) -> BudgetUpload:
        del self, content, filename, user
        row = BudgetUpload(
            cycle_id=cycle_id,
            org_unit_id=org_unit_id,
            uploader_id=uuid4(),
            version=1,
            file_path_enc=b"enc",
            file_hash=b"\x00" * 32,
            file_size_bytes=1024,
            row_count=3,
            status=UploadStatus.valid.value,
            uploaded_at=cycle.opened_at,
        )
        row.id = uuid4()
        return row

    monkeypatch.setattr(BudgetUploadService, "upload", _fake_upload)

    response = await budget_client.post(
        f"/api/v1/cycles/{cycle.id}/uploads/{unit.id}",
        files={"file": ("q1.xlsx", b"fake-bytes", "application/octet-stream")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 1
    assert body["row_count"] == 3
    assert body["status"] == "valid"


async def test_upload_returns_validation_envelope(
    budget_client: httpx.AsyncClient,
    budget_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Row errors surface as a 400 with ``UPLOAD_007`` envelope."""
    cycle, unit = _seed_app(budget_app)

    async def _fake_upload(*args: Any, **kwargs: Any) -> BudgetUpload:
        del args, kwargs
        raise BatchValidationError(
            "UPLOAD_007",
            errors=[
                {
                    "row": 2,
                    "column": "budget_amount",
                    "code": "UPLOAD_005",
                    "reason": "amount is not numeric",
                }
            ],
        )

    monkeypatch.setattr(BudgetUploadService, "upload", _fake_upload)

    response = await budget_client.post(
        f"/api/v1/cycles/{cycle.id}/uploads/{unit.id}",
        files={"file": ("bad.xlsx", b"x", "application/octet-stream")},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "UPLOAD_007"
    assert body["error"]["details"][0]["row"] == 2


async def test_upload_requires_filing_unit_role(
    budget_client: httpx.AsyncClient,
    budget_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST as CompanyReviewer is rejected with ``RBAC_001``."""
    cycle, unit = _seed_app(budget_app)

    reviewer = User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=b"\x00" * 32,
        name="Reviewer",
        email_enc=b"reviewer@example.com",
        email_hash=b"\x00" * 32,
        roles=[Role.CompanyReviewer.value],
        org_unit_id=None,
        is_active=True,
    )

    async def _fake_current_user(self: AuthService, request: object) -> User:
        del self, request
        return reviewer

    monkeypatch.setattr(AuthService, "current_user", _fake_current_user)

    response = await budget_client.post(
        f"/api/v1/cycles/{cycle.id}/uploads/{unit.id}",
        files={"file": ("q1.xlsx", b"x", "application/octet-stream")},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "RBAC_001"


# ---------------------------------------------------- GET /cycles/{id}/uploads/{unit}
async def test_list_versions_returns_payloads(
    budget_client: httpx.AsyncClient,
    budget_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET returns rows serialized as BudgetUploadRead."""
    cycle, unit = _seed_app(budget_app)

    async def _fake_list(
        self: BudgetUploadService,
        *,
        cycle_id: Any,
        org_unit_id: Any,
    ) -> list[BudgetUpload]:
        del self, cycle_id, org_unit_id
        rows: list[BudgetUpload] = []
        for version in (2, 1):
            row = BudgetUpload(
                cycle_id=cycle.id,
                org_unit_id=unit.id,
                uploader_id=uuid4(),
                version=version,
                file_path_enc=b"enc",
                file_hash=b"\x00" * 32,
                file_size_bytes=100,
                row_count=5,
                status=UploadStatus.valid.value,
                uploaded_at=cycle.opened_at,
            )
            row.id = uuid4()
            rows.append(row)
        return rows

    monkeypatch.setattr(BudgetUploadService, "list_versions", _fake_list)

    response = await budget_client.get(f"/api/v1/cycles/{cycle.id}/uploads/{unit.id}")
    assert response.status_code == 200
    body = response.json()
    assert [row["version"] for row in body] == [2, 1]


async def test_list_versions_scope_check_rejects_other_unit(
    budget_client: httpx.AsyncClient,
    budget_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A FilingUnitManager cannot list uploads for a different unit."""
    cycle, unit = _seed_app(budget_app)
    other_unit = make_org_unit(code="4099")
    session: FakeSession = budget_app.state._shared_session  # type: ignore[attr-defined]
    session.org_units.append(other_unit)

    scoped = User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=b"\x00" * 32,
        name="Filer",
        email_enc=b"f@example.com",
        email_hash=b"\x00" * 32,
        roles=[Role.FilingUnitManager.value],
        org_unit_id=unit.id,
        is_active=True,
    )

    async def _fake_current_user(self: AuthService, request: object) -> User:
        del self, request
        return scoped

    monkeypatch.setattr(AuthService, "current_user", _fake_current_user)

    response = await budget_client.get(f"/api/v1/cycles/{cycle.id}/uploads/{other_unit.id}")
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "RBAC_002"
