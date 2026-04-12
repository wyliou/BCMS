"""Persistence helpers for :mod:`app.domain.budget_uploads.service`.

Small, self-contained SQL helpers kept in a separate module so the
service file stays under the 500-line ceiling. Every helper accepts an
:class:`AsyncSession` and returns plain ORM rows / primitive dicts —
there is no hidden caching or session ownership.

The helpers are:

* :func:`list_versions` — newest-first list of uploads for one pair.
* :func:`get_latest` — single highest-version upload for one pair.
* :func:`get_latest_by_cycle` — cross-cycle map of
  ``(org_unit_id, account_code_id) → amount`` for the consolidated
  report (M7) to join budget amounts into its output.
* :func:`account_code_id_map` — service helper used by the upload
  persistence path to translate validated ``account_code`` strings into
  :class:`AccountCode` primary key ids.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.accounts.models import AccountCode
from app.domain.budget_uploads.models import BudgetLine, BudgetUpload

__all__ = [
    "account_code_id_map",
    "get_latest",
    "get_latest_by_cycle",
    "list_versions",
]


async def list_versions(
    db: AsyncSession,
    *,
    cycle_id: UUID,
    org_unit_id: UUID,
) -> list[BudgetUpload]:
    """Return every upload version for a ``(cycle, org_unit)`` pair.

    Args:
        db: Active async session.
        cycle_id: Target :class:`BudgetCycle` UUID.
        org_unit_id: Target :class:`OrgUnit` UUID.

    Returns:
        list[BudgetUpload]: Rows ordered newest-first (``version``
        descending).
    """
    stmt = (
        select(BudgetUpload)
        .where(BudgetUpload.cycle_id == cycle_id)
        .where(BudgetUpload.org_unit_id == org_unit_id)
        .order_by(BudgetUpload.version.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_latest(
    db: AsyncSession,
    *,
    cycle_id: UUID,
    org_unit_id: UUID,
) -> BudgetUpload | None:
    """Return the highest-version upload for a pair, or ``None``.

    Args:
        db: Active async session.
        cycle_id: Target cycle UUID.
        org_unit_id: Target org unit UUID.

    Returns:
        BudgetUpload | None: Latest row, or ``None`` when the pair has
        no uploads yet.
    """
    stmt = (
        select(BudgetUpload)
        .where(BudgetUpload.cycle_id == cycle_id)
        .where(BudgetUpload.org_unit_id == org_unit_id)
        .order_by(BudgetUpload.version.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def get_latest_by_cycle(
    db: AsyncSession,
    cycle_id: UUID,
) -> dict[tuple[UUID, UUID], Decimal]:
    """Aggregate the latest-version budget amounts for a cycle.

    Used by :class:`app.domain.consolidation.service.ConsolidatedReportService`
    (M7) to merge budget amounts into the cross-filing-unit view. The
    result is a map of ``(org_unit_id, account_code_id) → amount`` where
    only the rows belonging to the highest-version :class:`BudgetUpload`
    per ``org_unit_id`` are included.

    Args:
        db: Active async session.
        cycle_id: Target cycle UUID.

    Returns:
        dict[tuple[UUID, UUID], Decimal]: Aggregated map. Empty when the
        cycle has no uploads.
    """
    # Reason: do the max-version selection in Python rather than a
    # window-function subquery so the same code path works against both
    # Postgres (integration) and the FakeSession used by unit tests. The
    # volume is small (≤100 filing units × ≤1 upload per unit).
    uploads_stmt = (
        select(BudgetUpload)
        .where(BudgetUpload.cycle_id == cycle_id)
        .order_by(BudgetUpload.version.desc())
    )
    uploads_result = await db.execute(uploads_stmt)
    uploads = list(uploads_result.scalars().all())
    if not uploads:
        return {}

    latest_by_unit: dict[UUID, BudgetUpload] = {}
    for upload in uploads:
        # Reason: order_by version desc means the first seen row per
        # org_unit_id wins — matches SQL "max(version) per unit".
        latest_by_unit.setdefault(upload.org_unit_id, upload)

    if not latest_by_unit:  # pragma: no cover — defensive
        return {}

    lines_stmt = select(BudgetLine).where(
        BudgetLine.upload_id.in_([u.id for u in latest_by_unit.values()])
    )
    lines_result = await db.execute(lines_stmt)
    lines = list(lines_result.scalars().all())

    upload_to_unit: dict[UUID, UUID] = {u.id: u.org_unit_id for u in latest_by_unit.values()}
    aggregated: dict[tuple[UUID, UUID], Decimal] = {}
    for line in lines:
        org_unit_id = upload_to_unit[line.upload_id]
        key = (org_unit_id, line.account_code_id)
        aggregated[key] = aggregated.get(key, Decimal("0")) + line.amount
    return aggregated


async def account_code_id_map(
    db: AsyncSession,
    *,
    codes: set[str],
) -> dict[str, UUID]:
    """Return a ``{code: id}`` map for the requested account codes.

    Args:
        db: Active async session.
        codes: Set of account-code strings.

    Returns:
        dict[str, UUID]: Mapping; unknown codes are simply absent.
    """
    if not codes:
        return {}
    stmt = select(AccountCode.code, AccountCode.id).where(AccountCode.code.in_(codes))
    result = await db.execute(stmt)
    mapping: dict[str, UUID] = {}
    for row in result.all():
        code, code_id = row
        mapping[code] = code_id
    return mapping
