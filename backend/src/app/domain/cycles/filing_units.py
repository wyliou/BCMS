"""Filing-unit enumeration + manager-presence check (FR-002, CR-008).

This module owns **CR-008**: :func:`list_filing_units` first enumerates
ALL ``org_units WHERE is_filing_unit = TRUE`` (CR-017 — the boolean is
the source of truth, never ``level_code``), then LEFT JOINs to ``users``
so that ``has_manager=False`` rows are preserved for the caller to warn
about. CR-010 (the ``0000公司`` root unit is never a filing unit) is
enforced by additionally filtering on ``level_code != '0000'`` — even if
a seed-data mistake sets ``is_filing_unit=TRUE`` on the root, it still
falls out of the result set.

:class:`FilingUnitInfo` is a lightweight dataclass (not a Pydantic model)
because the orchestrator consumes the list synchronously in-process and
we want to avoid the serialization cost on hot paths. The API layer
converts it to a Pydantic response model at the route boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.models import OrgUnit, User
from app.core.security.roles import Role

__all__ = ["FilingUnitInfo", "list_filing_units"]


# Roles that qualify as a "manager" for FR-002 / CR-008 purposes.
_MANAGER_ROLES: frozenset[str] = frozenset(
    {
        Role.FilingUnitManager.value,
        Role.UplineReviewer.value,
        Role.FinanceAdmin.value,
        Role.SystemAdmin.value,
    }
)


@dataclass
class FilingUnitInfo:
    """Per-unit view returned by :func:`list_filing_units`.

    Attributes:
        org_unit_id: Primary key of the filing unit.
        code: Human-readable org code (e.g. ``"4023"``).
        name: Display name.
        has_manager: ``True`` iff at least one active :class:`User` row
            has ``org_unit_id`` pointing at this unit and a manager-
            qualified role in its ``roles`` JSONB array.
        excluded: ``True`` iff ``str(cycle_id)`` is present in this
            unit's ``excluded_for_cycle_ids`` JSONB list (FR-002).
        warnings: Opportunistic advisory strings surfaced to the UI
            (e.g. ``"missing-manager"``). Empty in the common case.
    """

    org_unit_id: UUID
    code: str
    name: str
    has_manager: bool
    excluded: bool
    warnings: list[str] = field(default_factory=list[str])


async def list_filing_units(
    db: AsyncSession,
    cycle_id: UUID,
) -> list[FilingUnitInfo]:
    """Enumerate every filing unit and report manager/exclusion status.

    Implementation order (CR-008):

    1. Fetch all ``org_units`` with ``is_filing_unit = TRUE`` and
       ``level_code != '0000'`` (CR-010 + CR-017).
    2. Fetch every :class:`User` whose ``org_unit_id`` is in the result
       set, in a single follow-up query, so the manager check is O(units)
       rather than N+1.
    3. For each unit compute ``has_manager`` (any user with a manager
       role), ``excluded`` (cycle id present in the JSONB list), and a
       ``warnings`` list.

    Args:
        db: Active async DB session.
        cycle_id: Target cycle — used for the exclusion check.

    Returns:
        list[FilingUnitInfo]: Sorted by ``code`` ascending. ``has_manager=
        False`` rows are NOT filtered — the caller must decide whether to
        block (CR-008).
    """
    stmt = (
        select(OrgUnit)
        .where(OrgUnit.is_filing_unit.is_(True))
        .where(OrgUnit.level_code != "0000")
        .order_by(OrgUnit.code.asc())
    )
    units = list((await db.execute(stmt)).scalars().all())
    if not units:
        return []

    unit_ids = [u.id for u in units]
    users_stmt = select(User).where(User.org_unit_id.in_(unit_ids)).where(User.is_active.is_(True))
    users = list((await db.execute(users_stmt)).scalars().all())

    # Reason: pre-group users by org_unit_id so the per-unit check below
    # is a single dict lookup instead of a linear scan.
    by_unit: dict[UUID, list[User]] = {}
    for user in users:
        if user.org_unit_id is None:
            continue
        by_unit.setdefault(user.org_unit_id, []).append(user)

    cycle_id_str = str(cycle_id)
    results: list[FilingUnitInfo] = []
    for unit in units:
        candidates = by_unit.get(unit.id, [])
        has_manager = _has_manager_role(candidates)
        excluded_list = list(unit.excluded_for_cycle_ids or [])
        excluded = cycle_id_str in excluded_list
        warnings: list[str] = []
        if not has_manager and not excluded:
            warnings.append("missing-manager")
        results.append(
            FilingUnitInfo(
                org_unit_id=unit.id,
                code=unit.code,
                name=unit.name,
                has_manager=has_manager,
                excluded=excluded,
                warnings=warnings,
            )
        )
    return results


def _has_manager_role(users: list[User]) -> bool:
    """Return whether any user in ``users`` carries a manager-qualified role.

    Args:
        users: Candidate :class:`User` rows attached to the same org unit.

    Returns:
        bool: ``True`` iff at least one user has one of the roles in
        :data:`_MANAGER_ROLES`.
    """
    for user in users:
        raw_roles = list(user.roles or [])
        if any(role in _MANAGER_ROLES for role in raw_roles):
            return True
    return False
