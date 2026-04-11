"""Cross-domain read helpers used by every importer (build-plan §5.4).

The only exported function today is :func:`org_unit_code_to_id_map`
(CR-018) — every importer that accepts a user-supplied ``dept_id`` /
``org_unit_code`` column translates it to the internal ``org_units.id``
UUID via this map. Keeping the lookup in one place guarantees all four
importers (``accounts`` / ``budget_uploads`` / ``personnel`` /
``shared_costs``) use the exact same query shape and cannot drift.

Per-request caching (recommended pattern)
-----------------------------------------
The map is small (≤100 rows in practice) but should still be loaded at
most once per HTTP request. The recommended pattern is a FastAPI
:class:`~fastapi.Depends` provider at the route layer:

.. code-block:: python

    async def get_org_unit_map(
        db: AsyncSession = Depends(get_session),
    ) -> dict[str, UUID]:
        return await org_unit_code_to_id_map(db)

Importers then receive the map as a constructor/function argument
(``validator.validate(rows, org_unit_codes=org_unit_map, ...)``) rather
than calling :func:`org_unit_code_to_id_map` per row. Do **not** wrap
this function in a module-level ``lru_cache`` — that would bleed across
requests and complicate testing.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.models import OrgUnit

__all__ = ["org_unit_code_to_id_map"]


async def org_unit_code_to_id_map(db: AsyncSession) -> dict[str, UUID]:
    """Return a mapping of ``org_units.code`` to ``org_units.id``.

    Executes a single ``SELECT id, code FROM org_units`` and materializes
    the result into a plain ``dict``. No filtering is applied — the
    caller (validator) is responsible for rejecting codes that are
    absent from the map and for checking ``is_filing_unit`` if needed.

    Args:
        db: Active async database session (injected via FastAPI
            ``Depends(get_session)``).

    Returns:
        dict[str, UUID]: Keys are ``org_units.code`` strings (e.g.
        ``"4023"``), values are :class:`uuid.UUID` instances. An empty
        dict is returned when the table contains no rows.
    """
    stmt = select(OrgUnit.code, OrgUnit.id)
    result = await db.execute(stmt)
    mapping: dict[str, UUID] = {}
    for row in result.all():
        code, unit_id = row
        mapping[code] = unit_id
    return mapping
