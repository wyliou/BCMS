"""Admin org-unit routes (SystemAdmin + FinanceAdmin).

The ``PATCH /admin/org-units/{id}`` endpoint ships here in Batch 2 even
though its consumer (FR-002 cycles service) lands in Batch 4. Spec
rationale:

* The per-cycle exclusion decision is a piece of *admin* metadata that
  does not depend on any cycle logic — it is just a JSONB list of
  cycle ids on the org-unit row.
* Batch 2 owns user/org-unit administration, so the route fits here.
* Batch 4 will read the ``excluded_for_cycle_ids`` column from
  :class:`app.core.security.models.OrgUnit` without any code change
  on this side.

All mutating routes follow CR-006 (commit first, audit on a side
session, return).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_utc
from app.core.security.models import OrgUnit, User
from app.core.security.rbac import require_role
from app.core.security.roles import Role
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService
from app.infra.db.session import get_session, get_session_factory

__all__ = ["router"]


router = APIRouter(prefix="/admin/org-units", tags=["admin", "org_units"])


class OrgUnitRead(BaseModel):
    """Serialized org-unit record.

    Attributes:
        id (UUID): Primary key.
        code (str): Human-readable org code.
        name (str): Display name.
        level_code (str): Hierarchy level code.
        parent_id (UUID | None): Parent org-unit id.
        is_filing_unit (bool): Whether this unit participates in filing.
        is_reviewer_only (bool): Whether this unit is review-only.
        excluded_for_cycle_ids (list[str]): Cycle ids this unit is
            excluded from per FR-002.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    level_code: str
    parent_id: UUID | None
    is_filing_unit: bool
    is_reviewer_only: bool
    excluded_for_cycle_ids: list[str]


class OrgUnitPatch(BaseModel):
    """Body accepted by ``PATCH /admin/org-units/{id}``.

    Attributes:
        excluded_for_cycle_ids (list[str] | None): New exclusion list.
            ``None`` means "leave unchanged".
    """

    excluded_for_cycle_ids: list[str] | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("", response_model=list[OrgUnitRead])
async def list_org_units(
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.SystemAdmin, Role.FinanceAdmin)),
) -> list[OrgUnitRead]:
    """Return every org unit (read-only).

    Args:
        db (AsyncSession): Injected DB session.
        _user (User): RBAC guard — SystemAdmin or FinanceAdmin.

    Returns:
        list[OrgUnitRead]: Serialized rows ordered by ``code``.
    """
    del _user
    stmt = select(OrgUnit).order_by(OrgUnit.code.asc())
    rows = list((await db.execute(stmt)).scalars().all())
    return [OrgUnitRead.model_validate(row) for row in rows]


@router.patch("/{org_unit_id}", response_model=OrgUnitRead)
async def patch_org_unit(
    org_unit_id: UUID,
    body: OrgUnitPatch,
    db: AsyncSession = Depends(get_session),
    actor: User = Depends(require_role(Role.SystemAdmin, Role.FinanceAdmin)),
) -> OrgUnitRead:
    """Update ``excluded_for_cycle_ids`` on an org unit (FR-002).

    Args:
        org_unit_id (UUID): Target org unit id.
        body (OrgUnitPatch): Patch body.
        db (AsyncSession): Injected DB session.
        actor (User): Admin performing the change.

    Returns:
        OrgUnitRead: The updated org unit.
    """
    row = await db.get(OrgUnit, org_unit_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "ORG_UNIT_NOT_FOUND"}})

    before_excluded = list(row.excluded_for_cycle_ids or [])
    if body.excluded_for_cycle_ids is not None:
        row.excluded_for_cycle_ids = [str(x) for x in body.excluded_for_cycle_ids]
    row.updated_at = now_utc()
    await db.flush()
    await db.commit()

    after_excluded = list(row.excluded_for_cycle_ids or [])
    await _audit_org_unit_updated(actor.id, row.id, before_excluded, after_excluded)
    return OrgUnitRead.model_validate(row)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _audit_org_unit_updated(
    actor_id: UUID,
    target_id: UUID,
    before_excluded: list[str],
    after_excluded: list[str],
) -> None:
    """Write an ORG_UNIT_UPDATED audit row on a fresh side session (CR-006).

    Args:
        actor_id (UUID): Admin user id.
        target_id (UUID): Org unit being modified.
        before_excluded (list[str]): Previous exclusion list.
        after_excluded (list[str]): New exclusion list.
    """
    factory = get_session_factory()
    async with factory() as db:
        service = AuditService(db)
        await service.record(
            action=AuditAction.ORG_UNIT_UPDATED,
            resource_type="org_unit",
            resource_id=target_id,
            user_id=actor_id,
            ip_address=None,
            details={
                "excluded_for_cycle_ids": {
                    "before": before_excluded,
                    "after": after_excluded,
                }
            },
        )
        await db.commit()
