"""Shared query helpers against ``budget_uploads`` (CR-026, CR-027).

This module centralises the "filing units with zero uploads for this
cycle" query so Batch 4 (:mod:`app.domain.cycles.reminders`) and Batch 6
(the consolidation orchestrator) call the SAME SQL. Any drift between
the two call sites would violate CR-026, so only this module is allowed
to know the join shape.

The query uses raw ``sqlalchemy.text`` SQL because Batch 5 has not yet
shipped the :class:`BudgetUpload` ORM mapping — we cannot depend on a
class that does not yet exist. The table name, column names, and the
``excluded_for_cycle_ids`` JSONB containment operator are verbatim from
the 0001 baseline migration and the 0002 exclusion-column migration.

CR-027 is enforced by the ``NOT EXISTS`` subquery: units with one *or
more* upload versions never appear in the result. CR-010 is enforced by
the ``level_code != '0000'`` filter. CR-017 is enforced by using the
``is_filing_unit`` boolean as the authoritative filter.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["unsubmitted_for_cycle"]


async def unsubmitted_for_cycle(
    db: AsyncSession,
    cycle_id: UUID,
) -> list[UUID]:
    """Return ``org_unit.id`` values that have no upload for ``cycle_id``.

    The returned ids exclude:

    * non-filing units (``is_filing_unit = FALSE``),
    * the ``0000公司`` root (``level_code = '0000'``),
    * units whose ``excluded_for_cycle_ids`` JSONB array contains the
      target cycle id, and
    * units that already have at least one row in ``budget_uploads`` for
      this ``(cycle_id, org_unit_id)`` pair (CR-027).

    Args:
        db: Active async DB session.
        cycle_id: Cycle to check against.

    Returns:
        list[UUID]: Deduped filing-unit ids with no upload for the
        cycle. Sorted by ``code`` ascending for deterministic output.
    """
    sql = text(
        """
        SELECT ou.id
        FROM org_units AS ou
        WHERE ou.is_filing_unit = TRUE
          AND ou.level_code != '0000'
          AND NOT EXISTS (
              SELECT 1
              FROM budget_uploads AS bu
              WHERE bu.cycle_id = :cycle_id
                AND bu.org_unit_id = ou.id
          )
          AND NOT (ou.excluded_for_cycle_ids @> CAST(:cycle_json AS jsonb))
        ORDER BY ou.code ASC
        """
    )
    params = {
        "cycle_id": str(cycle_id),
        "cycle_json": f'["{cycle_id}"]',
    }
    result = await db.execute(sql, params)
    rows = result.all()
    out: list[UUID] = []
    for row in rows:
        raw = row[0]
        out.append(raw if isinstance(raw, UUID) else UUID(str(raw)))
    return out
