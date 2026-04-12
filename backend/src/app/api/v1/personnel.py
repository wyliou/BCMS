"""FastAPI routes for :mod:`app.domain.personnel` (FR-024..FR-026).

Thin orchestration only — every business decision lives in
:class:`app.domain.personnel.service.PersonnelImportService`. The
router exposes three endpoints:

* ``POST /cycles/{cycle_id}/personnel-imports`` — multipart upload.
  Allowed roles: ``HRAdmin`` + ``SystemAdmin``.
* ``GET  /cycles/{cycle_id}/personnel-imports`` — list versions for a cycle.
* ``GET  /personnel-imports/{id}`` — single import detail.

Per CR-033, ``HRAdmin`` and ``SystemAdmin`` both have global scope so no
additional scope filter is applied at this layer for list/read endpoints.
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
from app.domain.personnel.service import PersonnelImportService
from app.infra.db.session import get_session

__all__ = ["router", "PersonnelImportRead"]


router = APIRouter(tags=["personnel"])


class PersonnelImportRead(BaseModel):
    """Read model for :class:`PersonnelBudgetUpload` rows returned by the API.

    Attributes:
        id: Upload UUID.
        cycle_id: Parent cycle UUID.
        uploader_user_id: User UUID of the importer.
        uploaded_at: UTC timestamp when the row was committed.
        filename: Original client-supplied filename.
        file_hash: Hex digest of the uploaded file content.
        version: Monotonic version integer per cycle.
        affected_org_units_summary: JSONB snapshot of affected units.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cycle_id: UUID
    uploader_user_id: UUID
    uploaded_at: datetime
    filename: str
    file_hash: str
    version: int
    affected_org_units_summary: Any


def _build_service(db: AsyncSession) -> PersonnelImportService:
    """Return a :class:`PersonnelImportService` bound to ``db``.

    Kept as a module-level helper so api tests can monkey-patch it
    (matches the pattern used by :mod:`app.api.v1.budget_uploads`).

    Args:
        db: Active :class:`AsyncSession`.

    Returns:
        PersonnelImportService: Freshly-constructed service.
    """
    return PersonnelImportService(db)


# ======================================================================
#              POST /cycles/{cycle_id}/personnel-imports
# ======================================================================
@router.post(
    "/cycles/{cycle_id}/personnel-imports",
    response_model=PersonnelImportRead,
    status_code=201,
)
async def import_personnel(
    cycle_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_role(
            Role.HRAdmin,
            Role.SystemAdmin,
        )
    ),
) -> PersonnelImportRead:
    """Upload a CSV/XLSX personnel budget import for a cycle.

    Args:
        cycle_id: Target :class:`BudgetCycle` UUID.
        file: Multipart CSV or XLSX file upload.
        db: Database session (FastAPI dependency).
        user: Authenticated HRAdmin or SystemAdmin.

    Returns:
        PersonnelImportRead: Persisted import payload with version.
    """
    content = await file.read()
    service = _build_service(db)
    upload = await service.import_(
        cycle_id=cycle_id,
        filename=file.filename or "import.csv",
        content=content,
        user=user,
    )
    return PersonnelImportRead.model_validate(upload)


# ======================================================================
#              GET /cycles/{cycle_id}/personnel-imports
# ======================================================================
@router.get(
    "/cycles/{cycle_id}/personnel-imports",
    response_model=list[PersonnelImportRead],
)
async def list_personnel_versions(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_role(
            Role.HRAdmin,
            Role.FinanceAdmin,
            Role.SystemAdmin,
            Role.CompanyReviewer,
            Role.ITSecurityAuditor,
        )
    ),
) -> list[PersonnelImportRead]:
    """Return every personnel import version for a cycle.

    Args:
        cycle_id: Target cycle UUID.
        db: Database session (FastAPI dependency).
        user: Authenticated reader.

    Returns:
        list[PersonnelImportRead]: Rows ordered by version ascending.
    """
    service = _build_service(db)
    rows = await service.list_versions(cycle_id)
    return [PersonnelImportRead.model_validate(row) for row in rows]


# ======================================================================
#              GET /personnel-imports/{id}
# ======================================================================
@router.get(
    "/personnel-imports/{id}",
    response_model=PersonnelImportRead,
)
async def get_personnel_import(
    id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_role(
            Role.HRAdmin,
            Role.FinanceAdmin,
            Role.SystemAdmin,
            Role.CompanyReviewer,
            Role.ITSecurityAuditor,
        )
    ),
) -> PersonnelImportRead:
    """Return a single personnel import row.

    Args:
        id: Target upload UUID.
        db: Database session (FastAPI dependency).
        user: Authenticated reader.

    Returns:
        PersonnelImportRead: Matching import row.

    Raises:
        NotFoundError: ``PERS_004`` when the row does not exist.
    """
    service = _build_service(db)
    row = await service.get(id)
    return PersonnelImportRead.model_validate(row)
