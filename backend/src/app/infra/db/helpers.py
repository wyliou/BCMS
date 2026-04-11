"""Small shared SQL helpers used by multiple domain modules.

The only helper in Batch 0 is :func:`next_version`, which computes the next
monotonic version number for an upload table under a set of filter columns
(``cycle_id``, ``org_unit_id``, ...). The helper must be called inside the
same transaction that inserts the new row; the caller's UNIQUE constraint on
``(cycle_id, ..., version)`` is the final safety net against concurrent
uploads.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InfraError

__all__ = ["next_version"]


async def next_version(
    db: AsyncSession,
    model: type,
    **filters: Any,
) -> int:
    """Return ``MAX(version) + 1`` over rows matching ``filters``.

    The caller must supply an :class:`AsyncSession` already participating in
    the same transaction that will insert the new row. Race safety relies on
    the calling table's UNIQUE constraint on ``(..., version)``; on a
    concurrent insert conflict the caller must retry.

    Args:
        db: Active async session inside an open transaction.
        model: SQLAlchemy ORM class exposing a ``version`` column and any
            columns mentioned in ``filters``.
        **filters: Column/value pairs to scope the MAX query (e.g.
            ``cycle_id=..., org_unit_id=...``).

    Returns:
        int: The next version number (``1`` when no rows match the filter).

    Raises:
        InfraError: ``SYS_001`` on database failure.
    """
    try:
        version_col = model.version
        stmt = select(func.coalesce(func.max(version_col), 0))
        for column_name, value in filters.items():
            stmt = stmt.where(getattr(model, column_name) == value)
        result = await db.execute(stmt)
        current_max = result.scalar_one()
        return int(current_max) + 1
    except SQLAlchemyError as exc:
        raise InfraError("SYS_001", f"next_version failed: {exc}") from exc
