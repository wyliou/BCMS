"""FastAPI routes for the account master + actuals import (FR-007, FR-008).

Thin orchestration only — every piece of business logic lives in
:class:`app.domain.accounts.service.AccountService`. The router exposes:

* ``GET  /accounts`` — list accounts (optional ``category`` filter).
* ``POST /accounts`` — create or update (upsert) via the natural key.
* ``GET  /accounts/{code}`` — fetch a single account by code.
* ``POST /cycles/{cycle_id}/actuals`` — multipart upload for the
  collect-then-report actuals importer.

Batch 3 merges the admin + read-only endpoints into a single router
because the business operations are cohesive (upsert is the only write
path, and it's scoped to ``FinanceAdmin`` / ``SystemAdmin``).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.models import User
from app.core.security.rbac import require_role
from app.core.security.roles import Role
from app.domain.accounts.models import AccountCategory
from app.domain.accounts.service import (
    AccountCodeRead,
    AccountCodeWrite,
    AccountService,
    ImportSummary,
)
from app.infra.db.session import get_session

__all__ = ["router", "cycles_router"]


router = APIRouter(prefix="/accounts", tags=["accounts"])
cycles_router = APIRouter(prefix="/cycles", tags=["accounts", "cycles"])


def _build_service(db: AsyncSession) -> AccountService:
    """Construct an :class:`AccountService` from an active session.

    Kept as a helper so api tests can monkeypatch it with a fake.

    Args:
        db: Active :class:`AsyncSession`.

    Returns:
        AccountService: Ready-to-use service bound to ``db``.
    """
    return AccountService(db)


# ------------------------------------------------------------------- GET /accounts
@router.get("", response_model=list[AccountCodeRead])
async def list_accounts(
    category: AccountCategory | None = None,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.FinanceAdmin, Role.SystemAdmin, Role.HRAdmin)),
) -> list[AccountCodeRead]:
    """Return every account code, optionally filtered by category.

    Args:
        category: Optional :class:`AccountCategory` filter.
        db: Database session (FastAPI dependency).
        _user: RBAC guard — any admin-tier role is permitted to read.

    Returns:
        list[AccountCodeRead]: Accounts sorted ascending by ``code``.
    """
    del _user
    service = _build_service(db)
    rows = await service.list(category=category)
    return [AccountCodeRead.model_validate(row) for row in rows]


# ------------------------------------------------------------- GET /accounts/{code}
@router.get("/{code}", response_model=AccountCodeRead)
async def get_account(
    code: str,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.FinanceAdmin, Role.SystemAdmin, Role.HRAdmin)),
) -> AccountCodeRead:
    """Return a single account code.

    Args:
        code: Account code string (natural key).
        db: Database session (FastAPI dependency).
        _user: RBAC guard.

    Returns:
        AccountCodeRead: Matching account row.
    """
    del _user
    service = _build_service(db)
    row = await service.get_by_code(code)
    return AccountCodeRead.model_validate(row)


# ------------------------------------------------------------------ POST /accounts
@router.post("", response_model=AccountCodeRead, status_code=201)
async def upsert_account(
    body: AccountCodeWrite,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(Role.FinanceAdmin, Role.SystemAdmin)),
) -> AccountCodeRead:
    """Create or update an account code via its natural key.

    Args:
        body: :class:`AccountCodeWrite` request body.
        db: Database session (FastAPI dependency).
        user: Authenticated user (FinanceAdmin/SystemAdmin).

    Returns:
        AccountCodeRead: The persisted row.
    """
    service = _build_service(db)
    row = await service.upsert(data=body, user=user)
    return AccountCodeRead.model_validate(row)


# ------------------------------------------------- POST /cycles/{id}/actuals
@cycles_router.post(
    "/{cycle_id}/actuals",
    response_model=ImportSummary,
)
async def import_actuals(
    cycle_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(Role.FinanceAdmin, Role.SystemAdmin)),
) -> ImportSummary:
    """Upload a CSV/XLSX of actual expenses for a cycle.

    Args:
        cycle_id: Target cycle UUID.
        file: Multipart file upload (CSV or XLSX).
        db: Database session (FastAPI dependency).
        user: Authenticated user (FinanceAdmin/SystemAdmin).

    Returns:
        ImportSummary: Row count + affected org units.
    """
    content = await file.read()
    service = _build_service(db)
    summary = await service.import_actuals(
        cycle_id=cycle_id,
        filename=file.filename or "upload.csv",
        content=content,
        user=user,
    )
    return summary
