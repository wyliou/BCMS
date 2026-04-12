"""FastAPI routes for :mod:`app.domain.shared_costs` (FR-027..FR-029).

Thin orchestration only — every business decision lives in
:class:`app.domain.shared_costs.service.SharedCostImportService`. The
router exposes three endpoints:

* ``POST /cycles/{cycle_id}/shared-cost-imports`` — upload.
  FinanceAdmin + SystemAdmin only (FR-027).
* ``GET  /cycles/{cycle_id}/shared-cost-imports`` — list versions.
* ``GET  /shared-cost-imports/{id}`` — single import detail.

Per CR-033 the scope filter is applied inside the service layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.models import User
from app.core.security.rbac import require_role
from app.core.security.roles import Role
from app.domain.shared_costs.service import SharedCostImportService
from app.infra.db.session import get_session

__all__ = ["router", "SharedCostUploadRead"]


router = APIRouter(tags=["shared_costs"])


class SharedCostUploadRead(BaseModel):
    """Read model for :class:`SharedCostUpload` rows returned by the API.

    Attributes:
        id: Upload UUID.
        cycle_id: Parent cycle UUID.
        uploader_user_id: User UUID of the uploader.
        uploaded_at: UTC timestamp when the row was committed.
        filename: Original filename.
        version: Monotonic version integer per cycle.
        affected_org_units_summary: JSONB diff summary dict.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cycle_id: UUID
    uploader_user_id: UUID
    uploaded_at: datetime
    filename: str
    version: int
    affected_org_units_summary: dict[str, Any]


def _build_service(db: AsyncSession) -> SharedCostImportService:
    """Return a :class:`SharedCostImportService` bound to ``db``.

    Kept as a module-level helper so api tests can monkeypatch it.

    Args:
        db: Active :class:`AsyncSession`.

    Returns:
        SharedCostImportService: Freshly-constructed service.
    """
    return SharedCostImportService(db)


# ======================================================================
#          POST /cycles/{cycle_id}/shared-cost-imports
# ======================================================================
@router.post(
    "/cycles/{cycle_id}/shared-cost-imports",
    response_model=SharedCostUploadRead,
    status_code=201,
)
async def import_shared_costs(
    cycle_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_role(
            Role.FinanceAdmin,
            Role.SystemAdmin,
        )
    ),
) -> SharedCostUploadRead:
    """Upload a CSV or XLSX shared cost import for a cycle.

    Args:
        cycle_id: Target :class:`BudgetCycle` UUID.
        file: Multipart CSV or XLSX file.
        db: Database session (FastAPI dependency).
        user: Authenticated FinanceAdmin or SystemAdmin.

    Returns:
        SharedCostUploadRead: Persisted upload payload.
    """
    content = await file.read()
    service = _build_service(db)
    upload = await service.import_(
        cycle_id=cycle_id,
        filename=file.filename or "upload.csv",
        content=content,
        user=user,
    )
    return SharedCostUploadRead.model_validate(upload)


# ======================================================================
#          GET /cycles/{cycle_id}/shared-cost-imports
# ======================================================================
@router.get(
    "/cycles/{cycle_id}/shared-cost-imports",
    response_model=list[SharedCostUploadRead],
)
async def list_shared_cost_imports(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_role(
            Role.FinanceAdmin,
            Role.SystemAdmin,
            Role.CompanyReviewer,
            Role.UplineReviewer,
            Role.ITSecurityAuditor,
        )
    ),
) -> list[SharedCostUploadRead]:
    """Return all shared cost import versions for a cycle.

    Args:
        cycle_id: Target cycle UUID.
        db: Database session (FastAPI dependency).
        user: Authenticated reader.

    Returns:
        list[SharedCostUploadRead]: Rows ordered by version ascending.
    """
    service = _build_service(db)
    rows = await service.list_versions(cycle_id)
    return [SharedCostUploadRead.model_validate(row) for row in rows]


# ======================================================================
#          GET /shared-cost-imports/{id}
# ======================================================================
@router.get(
    "/shared-cost-imports/{upload_id}",
    response_model=SharedCostUploadRead,
)
async def get_shared_cost_import(
    upload_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_role(
            Role.FinanceAdmin,
            Role.SystemAdmin,
            Role.CompanyReviewer,
            Role.UplineReviewer,
            Role.ITSecurityAuditor,
        )
    ),
) -> SharedCostUploadRead:
    """Return a single shared cost import by UUID.

    Args:
        upload_id: Target UUID.
        db: Database session (FastAPI dependency).
        user: Authenticated reader.

    Returns:
        SharedCostUploadRead: Matching upload row.
    """
    service = _build_service(db)
    row = await service.get(upload_id)
    return SharedCostUploadRead.model_validate(row)
