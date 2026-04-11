"""Filing-unit exclusion helper (FR-002).

The admin UI flips :attr:`OrgUnit.excluded_for_cycle_ids` entries from
two places — Batch 2's ``PATCH /admin/org-units/{id}`` route and the
cycles service (so Batch 4 routes can surface a focused "exclude this
unit for THIS cycle" action). Both call sites converge on
:func:`apply_exclusion` here, which enforces CR-006 (commit + audit)
and dedupes the JSONB list.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_utc
from app.core.errors import NotFoundError
from app.core.security.models import OrgUnit, User
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService

__all__ = ["apply_exclusion"]


async def apply_exclusion(
    db: AsyncSession,
    audit: AuditService,
    *,
    org_unit_id: UUID,
    cycle_id: UUID,
    excluded: bool,
    user: User,
) -> OrgUnit:
    """Toggle ``cycle_id`` on/off the unit's ``excluded_for_cycle_ids``.

    Args:
        db: Active async DB session.
        audit: Audit service used to record the decision row.
        org_unit_id: Target org unit id.
        cycle_id: Cycle whose exclusion is being toggled.
        excluded: ``True`` to add the cycle id; ``False`` to remove.
        user: Acting admin.

    Returns:
        OrgUnit: The updated org unit row.

    Raises:
        NotFoundError: ``CYCLE_001`` when the org unit does not exist.
    """
    row = await db.get(OrgUnit, org_unit_id)
    if row is None:
        raise NotFoundError("CYCLE_001", f"Org unit {org_unit_id} not found")
    before = list(row.excluded_for_cycle_ids or [])
    target = str(cycle_id)
    after = list(before)
    if excluded and target not in after:
        after.append(target)
    elif not excluded and target in after:
        after = [x for x in after if x != target]
    row.excluded_for_cycle_ids = after
    row.updated_at = now_utc()
    await db.commit()

    await audit.record(
        action=AuditAction.FILING_UNIT_EXCLUDED,
        resource_type="org_unit",
        resource_id=org_unit_id,
        user_id=user.id,
        details={
            "cycle_id": target,
            "excluded": excluded,
            "before": before,
            "after": after,
        },
    )
    await db.commit()
    return row


def validate_currency(value: str) -> str:
    """Validate a 3-letter ISO 4217 currency code (CR-023).

    Args:
        value: Candidate currency code.

    Returns:
        str: Uppercase canonical form.

    Raises:
        ValueError: When ``value`` is not exactly three ASCII letters.
    """
    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha() or not normalized.isascii():
        raise ValueError(f"reporting_currency must be a 3-letter ISO 4217 code; got {value!r}")
    return normalized
