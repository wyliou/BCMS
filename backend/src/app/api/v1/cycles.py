"""FastAPI routes for :mod:`app.domain.cycles` (FR-001..FR-006, FR-020).

Thin orchestration only — every business decision lives in
:class:`app.domain.cycles.service.CycleService`. The router exposes the
seven endpoints listed in the Batch-4 spec:

* ``POST   /cycles``                       — create Draft (FinanceAdmin, SystemAdmin).
* ``GET    /cycles``                       — list all cycles (any reader).
* ``GET    /cycles/{id}``                  — read one.
* ``POST   /cycles/{id}/open``             — transition Draft → Open.
* ``POST   /cycles/{id}/close``            — transition Open → Closed.
* ``POST   /cycles/{id}/reopen``           — SystemAdmin-only reopen window.
* ``PATCH  /cycles/{id}/reminders``        — set the reminder schedule.
* ``GET    /cycles/{id}/filing-units``     — list filing unit info rows.

The FR-002 per-cycle exclusion decision already lives in Batch 2's
``PATCH /admin/org-units/{id}`` route; Batch 4 does NOT re-ship that
endpoint. The :meth:`CycleService.set_exclusions` helper is callable from
there when a follow-up PR wires a more focused
``POST /admin/org-units/{id}/exclude`` route.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.models import User
from app.core.security.rbac import require_role
from app.core.security.roles import Role
from app.domain.cycles.models import BudgetCycle
from app.domain.cycles.service import CycleService, FilingUnitInfo
from app.infra.db.session import get_session

__all__ = ["router"]


router = APIRouter(prefix="/cycles", tags=["cycles"])


# ---------------------------------------------------------------------- schemas
class CycleCreateBody(BaseModel):
    """Request body for :func:`create_cycle` (FR-001)."""

    fiscal_year: int = Field(..., ge=2000, le=2999)
    deadline: date
    reporting_currency: str = Field(default="TWD", min_length=3, max_length=3)


class CycleReopenBody(BaseModel):
    """Request body for :func:`reopen_cycle` (FR-006, CR-037)."""

    reason: str = Field(..., min_length=1, max_length=500)


class ReminderPatchBody(BaseModel):
    """Request body for :func:`set_reminder_schedule_route` (FR-005)."""

    days_before: list[int] = Field(default_factory=list)


class CycleRead(BaseModel):
    """Serialized :class:`BudgetCycle` row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fiscal_year: int
    deadline: date
    reporting_currency: str
    status: str
    opened_at: str | None = None
    closed_at: str | None = None
    reopened_at: str | None = None

    @classmethod
    def from_orm_row(cls, row: BudgetCycle) -> CycleRead:
        """Construct a :class:`CycleRead` from an ORM row.

        Args:
            row: The ORM :class:`BudgetCycle` instance.

        Returns:
            CycleRead: Serialized response model.
        """
        return cls(
            id=row.id,
            fiscal_year=row.fiscal_year,
            deadline=row.deadline,
            reporting_currency=row.reporting_currency,
            status=row.status,
            opened_at=row.opened_at.isoformat() if row.opened_at else None,
            closed_at=row.closed_at.isoformat() if row.closed_at else None,
            reopened_at=row.reopened_at.isoformat() if row.reopened_at else None,
        )


class FilingUnitInfoRead(BaseModel):
    """Serialized :class:`FilingUnitInfo` row."""

    org_unit_id: UUID
    code: str
    name: str
    has_manager: bool
    excluded: bool
    warnings: list[str]

    @classmethod
    def from_info(cls, info: FilingUnitInfo) -> FilingUnitInfoRead:
        """Serialize a :class:`FilingUnitInfo` dataclass.

        Args:
            info: Source dataclass.

        Returns:
            FilingUnitInfoRead: Equivalent Pydantic row.
        """
        return cls(
            org_unit_id=info.org_unit_id,
            code=info.code,
            name=info.name,
            has_manager=info.has_manager,
            excluded=info.excluded,
            warnings=list(info.warnings),
        )


class CycleOpenResponse(BaseModel):
    """Response body for :func:`open_cycle`."""

    cycle: CycleRead
    filing_units: list[FilingUnitInfoRead]


class ReminderScheduleRead(BaseModel):
    """Serialized reminder schedule row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cycle_id: UUID
    days_before: int


# ---------------------------------------------------------------------- helpers
def _build_service(db: AsyncSession) -> CycleService:
    """Return a :class:`CycleService` bound to ``db``.

    Kept as a module-level helper so api tests can monkey-patch it.

    Args:
        db: Active :class:`AsyncSession`.

    Returns:
        CycleService: Freshly-constructed service.
    """
    return CycleService(db)


# ------------------------------------------------------------------------ routes
@router.post("", response_model=CycleRead, status_code=201)
async def create_cycle(
    body: CycleCreateBody,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(Role.SystemAdmin, Role.FinanceAdmin)),
) -> CycleRead:
    """Create a new Draft cycle (FR-001).

    Args:
        body: Request body.
        db: Injected DB session.
        user: Authenticated SystemAdmin or FinanceAdmin.

    Returns:
        CycleRead: Serialized new cycle.
    """
    service = _build_service(db)
    cycle = await service.create(
        fiscal_year=body.fiscal_year,
        deadline=body.deadline,
        reporting_currency=body.reporting_currency,
        user=user,
    )
    return CycleRead.from_orm_row(cycle)


@router.get("", response_model=list[CycleRead])
async def list_cycles(
    fiscal_year: int | None = None,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(
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
) -> list[CycleRead]:
    """Return every cycle, optionally filtered by ``fiscal_year``.

    Args:
        fiscal_year: Optional filter.
        db: Injected DB session.
        _user: Authenticated reader (any role).

    Returns:
        list[CycleRead]: Serialized rows.
    """
    del _user
    service = _build_service(db)
    rows = await service.list(fiscal_year=fiscal_year)
    return [CycleRead.from_orm_row(r) for r in rows]


@router.get("/{cycle_id}", response_model=CycleRead)
async def get_cycle(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(
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
) -> CycleRead:
    """Return a single cycle by id.

    Args:
        cycle_id: Target cycle id.
        db: Injected DB session.
        _user: Authenticated reader.

    Returns:
        CycleRead: Serialized row.
    """
    del _user
    service = _build_service(db)
    row = await service.get(cycle_id)
    return CycleRead.from_orm_row(row)


@router.post("/{cycle_id}/open", response_model=CycleOpenResponse)
async def open_cycle(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(Role.SystemAdmin, Role.FinanceAdmin)),
) -> CycleOpenResponse:
    """Transition a cycle to Open state (FR-003).

    Args:
        cycle_id: Target cycle id.
        db: Injected DB session.
        user: Acting admin.

    Returns:
        CycleOpenResponse: Updated cycle + filing unit list.
    """
    service = _build_service(db)
    cycle, _units = await service.open(cycle_id, user)
    infos = await service.list_filing_units(cycle_id)
    return CycleOpenResponse(
        cycle=CycleRead.from_orm_row(cycle),
        filing_units=[FilingUnitInfoRead.from_info(info) for info in infos],
    )


@router.post("/{cycle_id}/close", response_model=CycleRead)
async def close_cycle(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(Role.SystemAdmin, Role.FinanceAdmin)),
) -> CycleRead:
    """Transition a cycle to Closed state (FR-006).

    Args:
        cycle_id: Target cycle id.
        db: Injected DB session.
        user: Acting admin.

    Returns:
        CycleRead: Updated row.
    """
    service = _build_service(db)
    cycle = await service.close(cycle_id, user)
    return CycleRead.from_orm_row(cycle)


@router.post("/{cycle_id}/reopen", response_model=CycleRead)
async def reopen_cycle(
    cycle_id: UUID,
    body: CycleReopenBody,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(Role.SystemAdmin)),
) -> CycleRead:
    """Reopen a Closed cycle within the window (CR-037). SystemAdmin only.

    Args:
        cycle_id: Target cycle id.
        body: Reason payload.
        db: Injected DB session.
        user: SystemAdmin actor.

    Returns:
        CycleRead: Updated row.
    """
    service = _build_service(db)
    cycle = await service.reopen(cycle_id, body.reason, user)
    return CycleRead.from_orm_row(cycle)


@router.patch("/{cycle_id}/reminders", response_model=list[ReminderScheduleRead])
async def set_reminder_schedule_route(
    cycle_id: UUID,
    body: ReminderPatchBody,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(Role.SystemAdmin, Role.FinanceAdmin)),
) -> list[ReminderScheduleRead]:
    """Replace the reminder schedule for a cycle (FR-005).

    Args:
        cycle_id: Target cycle id.
        body: Schedule payload (empty list disables reminders).
        db: Injected DB session.
        user: Acting admin.

    Returns:
        list[ReminderScheduleRead]: Serialized rows (empty on disable).
    """
    service = _build_service(db)
    rows = await service.set_reminder_schedule(cycle_id, body.days_before, user)
    return [
        ReminderScheduleRead(id=row.id, cycle_id=row.cycle_id, days_before=row.days_before)
        for row in rows
    ]


@router.get("/{cycle_id}/filing-units", response_model=list[FilingUnitInfoRead])
async def get_filing_units(
    cycle_id: UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.SystemAdmin, Role.FinanceAdmin)),
) -> list[FilingUnitInfoRead]:
    """Return filing-unit info rows for ``cycle_id``.

    Args:
        cycle_id: Target cycle id.
        db: Injected DB session.
        _user: Acting admin.

    Returns:
        list[FilingUnitInfoRead]: Serialized filing unit rows.
    """
    del _user
    service = _build_service(db)
    infos = await service.list_filing_units(cycle_id)
    return [FilingUnitInfoRead.from_info(i) for i in infos]


# Batch 2 shipped ``PATCH /admin/org-units/{id}`` for FR-002
# per-cycle exclusion. This module intentionally does NOT re-ship that
# route — :meth:`CycleService.set_exclusions` is the helper to call from
# any follow-up ``POST /admin/org-units/{id}/exclude`` wiring.
