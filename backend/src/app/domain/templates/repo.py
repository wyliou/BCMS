"""Persistence helpers for :mod:`app.domain.templates.service`.

The helpers own the narrow SQL used by the service layer:

* ``upsert_generated_row`` — delete any prior row and insert a fresh
  generated one; used on both ``generate_for_cycle`` and ``regenerate``.
* ``upsert_error_row`` — delete the prior row and insert a
  generation-error row; used when per-unit isolation catches an
  exception.
* ``fetch_template`` — load the unique row for a ``(cycle, org_unit)``
  pair.
* ``fetch_actuals`` — map every ``actual_expense`` row for one
  ``(cycle, org_unit)`` pair into ``{account_code_id: amount}``.

Keeping the SQL here lets the service stay under the 500-line ceiling
and makes the compile-statement shapes easier to verify against the
in-memory ``FakeSession`` unit-test stand-in.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_utc
from app.core.security.models import User
from app.domain.accounts.models import ActualExpense
from app.domain.templates.models import ExcelTemplate
from app.infra.crypto import encrypt_field

__all__ = [
    "fetch_actuals",
    "fetch_template",
    "upsert_error_row",
    "upsert_generated_row",
]


# Reason: the baseline schema forbids empty plaintext in ``file_path_enc``;
# use a short sentinel so generation-error rows still round-trip cleanly
# through :func:`app.infra.crypto.decrypt_field`.
_ERROR_PLACEHOLDER: bytes = b"<error>"


async def fetch_template(
    db: AsyncSession,
    *,
    cycle_id: UUID,
    org_unit_id: UUID,
) -> ExcelTemplate | None:
    """Return the unique :class:`ExcelTemplate` row for a pair, or ``None``.

    Args:
        db: Active async session.
        cycle_id: Target cycle id.
        org_unit_id: Target filing unit id.

    Returns:
        ExcelTemplate | None: Matching row, or ``None`` when absent.
    """
    stmt = select(ExcelTemplate).where(
        ExcelTemplate.cycle_id == cycle_id,
        ExcelTemplate.org_unit_id == org_unit_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def fetch_actuals(
    db: AsyncSession,
    *,
    cycle_id: UUID,
    org_unit_id: UUID,
) -> dict[UUID, Decimal]:
    """Return the ``(account_code_id → amount)`` map for one unit.

    Missing entries are NOT prefilled here — the builder handles the
    CR-034 zero default so an absent row still produces a ``0`` cell in
    the generated workbook.

    Args:
        db: Active async session.
        cycle_id: Target cycle id.
        org_unit_id: Target filing unit id.

    Returns:
        dict[UUID, Decimal]: Actuals keyed by :class:`AccountCode.id`.
    """
    stmt = select(ActualExpense.account_code_id, ActualExpense.amount).where(
        ActualExpense.cycle_id == cycle_id,
        ActualExpense.org_unit_id == org_unit_id,
    )
    result = await db.execute(stmt)
    return {row[0]: row[1] for row in result.all()}


async def upsert_generated_row(
    db: AsyncSession,
    *,
    cycle_id: UUID,
    org_unit_id: UUID,
    storage_key: str,
    content: bytes,
    user: User,
) -> ExcelTemplate:
    """Delete any existing row and insert a fresh generated one.

    The baseline schema owns the ``uq_templates_cycle_org`` unique
    constraint; a simple delete-then-insert is the cleanest way to
    implement regenerate semantics without racing on UPDATE.

    Args:
        db: Active async session (caller commits).
        cycle_id: Target cycle id.
        org_unit_id: Target filing unit id.
        storage_key: Opaque key returned by :func:`app.infra.storage.save`.
        content: Raw workbook bytes (used for the SHA-256 digest).
        user: Acting user (threaded into ``generated_by``).

    Returns:
        ExcelTemplate: The newly persisted row (flushed, so ``id`` is
        populated).
    """
    await db.execute(
        delete(ExcelTemplate).where(
            ExcelTemplate.cycle_id == cycle_id,
            ExcelTemplate.org_unit_id == org_unit_id,
        )
    )
    now = now_utc()
    row = ExcelTemplate(
        cycle_id=cycle_id,
        org_unit_id=org_unit_id,
        file_path_enc=encrypt_field(storage_key.encode("utf-8")),
        file_hash=hashlib.sha256(content).digest(),
        generated_at=now,
        generated_by=user.id,
        download_count=0,
        generation_error=None,
    )
    db.add(row)
    await db.flush()
    return row


async def upsert_error_row(
    db: AsyncSession,
    *,
    cycle_id: UUID,
    org_unit_id: UUID,
    user: User,
    error_message: str,
) -> ExcelTemplate:
    """Delete any existing row and insert a fresh generation-error row.

    Args:
        db: Active async session (caller commits).
        cycle_id: Target cycle id.
        org_unit_id: Target filing unit id.
        user: Acting user (threaded into ``generated_by``).
        error_message: Truncated human-readable message — truncated to
            500 characters so the DB column never overflows.

    Returns:
        ExcelTemplate: The persisted error row (flushed, so ``id`` is
        populated).
    """
    await db.execute(
        delete(ExcelTemplate).where(
            ExcelTemplate.cycle_id == cycle_id,
            ExcelTemplate.org_unit_id == org_unit_id,
        )
    )
    now = now_utc()
    row = ExcelTemplate(
        cycle_id=cycle_id,
        org_unit_id=org_unit_id,
        file_path_enc=encrypt_field(_ERROR_PLACEHOLDER),
        file_hash=b"\x00" * 32,
        generated_at=now,
        generated_by=user.id,
        download_count=0,
        generation_error=error_message[:500],
    )
    db.add(row)
    await db.flush()
    return row
