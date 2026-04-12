"""FastAPI routes for :mod:`app.domain.templates` (FR-009, FR-010).

Thin orchestration only — every piece of business logic lives in
:class:`app.domain.templates.service.TemplateService`. The router
exposes the two endpoints listed in the Batch-5 M3 spec:

* ``POST /cycles/{cycle_id}/templates/{org_unit_id}/regenerate`` —
  regenerate a single unit's template (FinanceAdmin + SystemAdmin).
* ``GET  /cycles/{cycle_id}/templates/{org_unit_id}/download`` —
  scope-checked download (any authenticated role; service layer
  enforces ``scoped_org_units``).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.models import User
from app.core.security.rbac import require_role
from app.core.security.roles import Role
from app.domain.cycles.models import BudgetCycle, OrgUnit
from app.domain.templates.service import TemplateGenerationResult, TemplateService
from app.infra.db.session import get_session

__all__ = ["router"]


router = APIRouter(prefix="/cycles", tags=["templates"])


_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _build_service(db: AsyncSession) -> TemplateService:
    """Return a :class:`TemplateService` bound to ``db``.

    Kept as a module-level helper so api tests can monkey-patch it
    (matches the pattern used by ``api.v1.cycles._build_service``).

    Args:
        db: Active :class:`AsyncSession`.

    Returns:
        TemplateService: Freshly-constructed service.
    """
    return TemplateService(db)


@router.post(
    "/{cycle_id}/templates/{org_unit_id}/regenerate",
    response_model=TemplateGenerationResult,
)
async def regenerate_template(
    cycle_id: UUID,
    org_unit_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(Role.FinanceAdmin, Role.SystemAdmin)),
) -> TemplateGenerationResult:
    """Regenerate a single filing unit's template (FR-009).

    The service layer fetches the cycle + org unit fresh and reuses
    the per-unit generation path, so success and error semantics
    match :meth:`TemplateService.generate_for_cycle` exactly.

    Args:
        cycle_id: Target cycle id.
        org_unit_id: Target filing unit id.
        db: Injected DB session.
        user: Authenticated FinanceAdmin or SystemAdmin.

    Returns:
        TemplateGenerationResult: Success or captured-error result.
    """
    service = _build_service(db)
    cycle = await db.get(BudgetCycle, cycle_id)
    org_unit = await db.get(OrgUnit, org_unit_id)
    if cycle is None or org_unit is None:
        from app.core.errors import NotFoundError

        raise NotFoundError(
            "TPL_002",
            f"cycle={cycle_id} or org_unit={org_unit_id} not found",
        )
    return await service.regenerate(cycle=cycle, org_unit=org_unit, user=user)


@router.get("/{cycle_id}/templates/{org_unit_id}/download")
async def download_template(
    cycle_id: UUID,
    org_unit_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_role(
            Role.SystemAdmin,
            Role.FinanceAdmin,
            Role.HRAdmin,
            Role.UplineReviewer,
            Role.FilingUnitManager,
            Role.CompanyReviewer,
        )
    ),
) -> Response:
    """Download a generated template (FR-010, CR-011).

    The role guard here permits every non-auditor reader role; the
    per-org-unit scope check lives inside
    :meth:`TemplateService.download` so the service raises
    ``RBAC_002`` for any unit outside the caller's scope.

    Args:
        cycle_id: Target cycle id.
        org_unit_id: Target filing unit id.
        db: Injected DB session.
        user: Authenticated caller with any reader role.

    Returns:
        Response: ``200 OK`` with the ``.xlsx`` bytes and a
        ``Content-Disposition: attachment`` header so browsers trigger
        the file download dialog.
    """
    service = _build_service(db)
    filename, content = await service.download(
        cycle_id=cycle_id,
        org_unit_id=org_unit_id,
        user=user,
    )
    return Response(
        content=content,
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
