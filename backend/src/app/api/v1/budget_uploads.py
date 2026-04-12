"""FastAPI routes for :mod:`app.domain.budget_uploads` (FR-011..FR-013).

Thin orchestration only — every business decision lives in
:class:`app.domain.budget_uploads.service.BudgetUploadService`. The
router exposes three endpoints:

* ``POST /cycles/{cycle_id}/uploads/{org_unit_id}`` — multipart upload
  (``FilingUnitManager`` + ``FinanceAdmin`` + ``SystemAdmin``).
* ``GET  /cycles/{cycle_id}/uploads/{org_unit_id}`` — list versions for
  a ``(cycle, org_unit)`` pair.
* ``GET  /uploads/{upload_id}`` — single upload detail.

Per CR-033, the scope filter is applied inside the service layer (the
``upload`` path calls ``RBAC.scoped_org_units`` via
:meth:`BudgetUploadService._assert_scope`). The list endpoint re-runs
the scope check here so reviewers can never list a unit outside their
visible set.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.core.security.models import User
from app.core.security.rbac import ALL_SCOPES, require_role, scoped_org_units
from app.core.security.roles import Role
from app.domain.budget_uploads.service import BudgetUploadService
from app.infra.db.session import get_session

__all__ = ["router", "BudgetUploadRead"]


router = APIRouter(tags=["budget_uploads"])


class BudgetUploadRead(BaseModel):
    """Read model for :class:`BudgetUpload` rows returned by the API.

    Attributes:
        id: Upload UUID.
        cycle_id: Parent cycle UUID.
        org_unit_id: Parent org unit UUID.
        version: Monotonic version integer per ``(cycle, org_unit)``.
        uploader_id: User UUID of the uploader.
        row_count: Number of :class:`BudgetLine` rows persisted.
        file_size_bytes: Raw size of the uploaded bytes.
        status: Upload status string (``valid`` in practice).
        uploaded_at: UTC timestamp when the row was committed.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cycle_id: UUID
    org_unit_id: UUID
    version: int
    uploader_id: UUID
    row_count: int
    file_size_bytes: int
    status: str
    uploaded_at: datetime


def _build_service(db: AsyncSession) -> BudgetUploadService:
    """Return a :class:`BudgetUploadService` bound to ``db``.

    Kept as a module-level helper so api tests can monkey-patch it
    (matches the pattern used by :mod:`app.api.v1.templates`).

    Args:
        db: Active :class:`AsyncSession`.

    Returns:
        BudgetUploadService: Freshly-constructed service.
    """
    return BudgetUploadService(db)


# ======================================================================
#                      POST /cycles/{id}/uploads/{unit}
# ======================================================================
@router.post(
    "/cycles/{cycle_id}/uploads/{org_unit_id}",
    response_model=BudgetUploadRead,
    status_code=201,
)
async def upload_budget(
    cycle_id: UUID,
    org_unit_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_role(
            Role.FilingUnitManager,
            Role.FinanceAdmin,
            Role.SystemAdmin,
        )
    ),
) -> BudgetUploadRead:
    """Upload a ``.xlsx`` budget workbook for one ``(cycle, org_unit)``.

    Args:
        cycle_id: Target :class:`BudgetCycle` UUID.
        org_unit_id: Target :class:`OrgUnit` UUID.
        file: Multipart ``.xlsx`` file upload.
        db: Database session (FastAPI dependency).
        user: Authenticated uploader.

    Returns:
        BudgetUploadRead: Persisted upload payload.
    """
    content = await file.read()
    service = _build_service(db)
    upload = await service.upload(
        cycle_id=cycle_id,
        org_unit_id=org_unit_id,
        filename=file.filename or "upload.xlsx",
        content=content,
        user=user,
    )
    return BudgetUploadRead.model_validate(upload)


# ======================================================================
#                      GET /cycles/{id}/uploads/{unit}
# ======================================================================
@router.get(
    "/cycles/{cycle_id}/uploads/{org_unit_id}",
    response_model=list[BudgetUploadRead],
)
async def list_upload_versions(
    cycle_id: UUID,
    org_unit_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_role(
            Role.FilingUnitManager,
            Role.FinanceAdmin,
            Role.SystemAdmin,
            Role.UplineReviewer,
            Role.CompanyReviewer,
        )
    ),
) -> list[BudgetUploadRead]:
    """Return every upload version for a ``(cycle, org_unit)`` pair.

    Enforces CR-033 at the route level — scoped roles may only list
    units inside their :func:`scoped_org_units` result.

    Args:
        cycle_id: Target cycle UUID.
        org_unit_id: Target org unit UUID.
        db: Database session (FastAPI dependency).
        user: Authenticated reader.

    Returns:
        list[BudgetUploadRead]: Rows ordered newest-first.
    """
    scope = await scoped_org_units(user, db)
    if scope is not ALL_SCOPES and org_unit_id not in scope:
        raise ForbiddenError(
            "RBAC_002",
            f"org_unit {org_unit_id} outside permitted scope",
        )
    service = _build_service(db)
    rows = await service.list_versions(
        cycle_id=cycle_id,
        org_unit_id=org_unit_id,
    )
    return [BudgetUploadRead.model_validate(row) for row in rows]


# ======================================================================
#                          GET /uploads/{id}
# ======================================================================
@router.get(
    "/uploads/{upload_id}",
    response_model=BudgetUploadRead,
)
async def get_upload(
    upload_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_role(
            Role.FilingUnitManager,
            Role.FinanceAdmin,
            Role.SystemAdmin,
            Role.UplineReviewer,
            Role.CompanyReviewer,
            Role.ITSecurityAuditor,
        )
    ),
) -> BudgetUploadRead:
    """Return a single upload row.

    Args:
        upload_id: Target UUID.
        db: Database session.
        user: Authenticated reader.

    Returns:
        BudgetUploadRead: Matching upload row.
    """
    service = _build_service(db)
    row = await service.get(upload_id)
    # CR-033: the per-upload read path still runs a scope check so
    # scoped roles cannot fetch an upload belonging to a different unit.
    scope = await scoped_org_units(user, db)
    if scope is not ALL_SCOPES and row.org_unit_id not in scope:
        raise ForbiddenError(
            "RBAC_002",
            f"upload {upload_id} outside permitted scope",
        )
    return BudgetUploadRead.model_validate(row)
