"""FastAPI routes for the per-role dashboard (FR-004, FR-014).

Thin orchestration — every piece of business logic lives in
:class:`app.domain.consolidation.dashboard.DashboardService`. The route
exposes a single GET endpoint scoped to any authenticated role; the
service enforces the CR-011 scope filter.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.models import User
from app.core.security.rbac import require_role
from app.core.security.roles import Role
from app.domain.consolidation.dashboard import (
    DashboardFilters,
    DashboardResponse,
    DashboardService,
    DashboardStatus,
)
from app.infra.db.session import get_session

__all__ = ["router"]


router = APIRouter(prefix="/cycles", tags=["dashboard"])


def _build_service(db: AsyncSession) -> DashboardService:
    """Return a :class:`DashboardService` bound to ``db``.

    Args:
        db: Active :class:`AsyncSession`.

    Returns:
        DashboardService: Fresh service instance.
    """
    return DashboardService(db)


@router.get("/{cycle_id}/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    cycle_id: UUID,
    status: DashboardStatus | None = Query(default=None),
    org_unit_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(
        require_role(
            Role.SystemAdmin,
            Role.FinanceAdmin,
            Role.HRAdmin,
            Role.UplineReviewer,
            Role.CompanyReviewer,
            Role.FilingUnitManager,
            Role.ITSecurityAuditor,
        )
    ),
) -> DashboardResponse:
    """Return the per-role dashboard for ``cycle_id`` (FR-004, FR-014).

    Args:
        cycle_id: Target cycle UUID.
        status: Optional status filter.
        org_unit_id: Optional single-unit filter.
        limit: Page size.
        offset: Page offset.
        db: Injected DB session.
        user: Authenticated caller (any reader).

    Returns:
        DashboardResponse: Scoped response payload.
    """
    filters = DashboardFilters(
        status=status,
        org_unit_id=org_unit_id,
        limit=limit,
        offset=offset,
    )
    service = _build_service(db)
    return await service.status_for_user(
        cycle_id=cycle_id,
        user=user,
        filters=filters,
    )
