"""Shared-cost import helpers.

Extracted from :mod:`app.domain.shared_costs.service` to keep each
source file under the 500-line hard limit.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.models import OrgUnit, User
from app.domain.accounts.models import AccountCode
from app.domain.shared_costs.models import SharedCostLine

__all__ = [
    "build_lines_data",
    "ephemeral_lines",
    "aggregate_by_unit",
    "fetch_lines",
    "account_code_id_map",
    "resolve_manager",
    "resolve_unit_codes",
    "extract_email",
]

_LOG = structlog.get_logger(__name__)


def build_lines_data(
    rows: list[dict[str, Any]],
    code_id_map: dict[str, UUID],
) -> list[dict[str, Any]]:
    """Translate validated rows into line dicts with resolved UUIDs.

    Args:
        rows: Validated row dicts.
        code_id_map: ``{account_code: UUID}`` map.

    Returns:
        list[dict[str, Any]]: Resolved dicts.
    """
    result: list[dict[str, Any]] = []
    for row in rows:
        code = str(row["account_code"])
        account_code_id = code_id_map.get(code)
        if account_code_id is None:
            _LOG.warning("shared_cost.account_code_not_in_map", code=code)
            continue
        result.append(
            {
                "org_unit_id": row["org_unit_id"],
                "account_code_id": account_code_id,
                "amount": row["amount"],
            }
        )
    return result


def ephemeral_lines(lines_data: list[dict[str, Any]]) -> list[SharedCostLine]:
    """Construct ephemeral SharedCostLine objects for diff computation.

    Args:
        lines_data: Pre-resolved line dicts.

    Returns:
        list[SharedCostLine]: Ephemeral ORM instances.
    """
    lines: list[SharedCostLine] = []
    upload_placeholder = uuid4()
    for data in lines_data:
        line = SharedCostLine(
            upload_id=upload_placeholder,
            org_unit_id=data["org_unit_id"],
            account_code_id=data["account_code_id"],
            amount=data["amount"],
        )
        lines.append(line)
    return lines


def aggregate_by_unit(lines: list[SharedCostLine]) -> dict[UUID, Decimal]:
    """Aggregate line amounts by org_unit_id.

    Args:
        lines: SharedCostLine rows.

    Returns:
        dict[UUID, Decimal]: Summed amounts per org unit.
    """
    totals: dict[UUID, Decimal] = {}
    for line in lines:
        totals[line.org_unit_id] = totals.get(line.org_unit_id, Decimal("0")) + line.amount
    return totals


async def fetch_lines(
    db: AsyncSession,
    *,
    upload_id: UUID,
) -> list[SharedCostLine]:
    """Return all lines for a given upload.

    Args:
        db: Active async session.
        upload_id: Target upload UUID.

    Returns:
        list[SharedCostLine]: All lines for the upload.
    """
    stmt = select(SharedCostLine).where(SharedCostLine.upload_id == upload_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def account_code_id_map(
    db: AsyncSession,
    *,
    codes: set[str],
) -> dict[str, UUID]:
    """Return a ``{code: id}`` map for the requested account codes.

    Args:
        db: Active async session.
        codes: Set of account-code strings to resolve.

    Returns:
        dict[str, UUID]: Mapping; unknown codes are absent.
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


async def resolve_manager(
    org_unit_id: UUID,
    db: AsyncSession,
) -> User | None:
    """Walk the org-unit parent chain to find a manager user.

    Args:
        org_unit_id: Starting org unit UUID.
        db: Active async session.

    Returns:
        User | None: Manager user, or ``None``.
    """
    visited: set[UUID] = set()
    current_id: UUID | None = org_unit_id
    while current_id is not None and current_id not in visited:
        visited.add(current_id)
        stmt = select(User).where(
            User.org_unit_id == current_id,
            User.is_active.is_(True),
        )
        result = await db.execute(stmt)
        user = result.scalars().first()
        if user is not None:
            return user
        unit = await db.get(OrgUnit, current_id)
        if unit is None:
            break
        current_id = unit.parent_id
    return None


async def resolve_unit_codes(
    db: AsyncSession,
    unit_ids: list[UUID],
) -> list[str]:
    """Resolve a list of org_unit UUIDs to their codes.

    Args:
        db: Active async session.
        unit_ids: List of org unit UUIDs.

    Returns:
        list[str]: Corresponding org unit codes.
    """
    if not unit_ids:
        return []
    stmt = select(OrgUnit.code).where(OrgUnit.id.in_(unit_ids))
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


def extract_email(user: User) -> str | None:
    """Best-effort email decode for notification dispatch.

    Args:
        user: User whose email is being resolved.

    Returns:
        str | None: Decoded email, or ``None``.
    """
    raw = user.email_enc or b""
    if not raw:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if "@" not in text:
        return None
    return text
