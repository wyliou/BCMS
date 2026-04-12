"""Personnel import helpers.

Extracted from :mod:`app.domain.personnel.service` to keep each
source file under the 500-line hard limit.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.roles import Role
from app.domain.accounts.models import AccountCode

__all__ = [
    "build_affected_summary",
    "account_code_id_map",
    "get_finance_admin_recipients",
]

_LOG = structlog.get_logger(__name__)


def build_affected_summary(
    rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Compute the affected_org_units_summary from validated rows.

    Args:
        rows: Validated rows with ``org_unit_id``, ``account_code``,
            and ``amount``.

    Returns:
        list[dict[str, str]]: One entry per distinct org_unit_id.
    """
    totals: dict[UUID, Decimal] = {}
    for row in rows:
        uid: UUID = row["org_unit_id"]
        amount: Decimal = row["amount"]
        totals[uid] = totals.get(uid, Decimal("0")) + amount

    return [{"org_unit_id": str(uid), "total_amount": str(total)} for uid, total in totals.items()]


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
        dict[str, UUID]: Mapping from code string to UUID.
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


async def get_finance_admin_recipients(
    db: AsyncSession,
) -> list[tuple[UUID, str]]:
    """Query User rows with FinanceAdmin role and extract emails.

    Args:
        db: Active async session.

    Returns:
        list[tuple[UUID, str]]: ``(user_id, email)`` tuples.
    """
    from app.core.security.models import User as UserModel

    stmt = select(UserModel).where(UserModel.is_active.is_(True))
    result = await db.execute(stmt)
    users = list(result.scalars().all())

    recipients: list[tuple[UUID, str]] = []
    for user in users:
        if Role.FinanceAdmin.value not in (user.roles or []):
            continue
        raw = user.email_enc or b""
        if not raw:
            continue
        try:
            email = raw.decode("utf-8")
        except UnicodeDecodeError:
            _LOG.warning("personnel_import.bad_email_enc", user_id=str(user.id))
            continue
        if "@" not in email:
            continue
        recipients.append((user.id, email))
    return recipients
