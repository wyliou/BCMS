"""SQLAlchemy ORM models for the ``account_codes`` and ``actual_expenses`` tables.

Mirrors the Alembic baseline (``alembic/versions/0001_baseline.py``)
column-for-column so the ORM round-trips cleanly against both the real
Postgres schema and the portable unit-test schema. :class:`AccountCategory`
is the **CR-020** owner — every category comparison across the backend
must use these enum members directly (no bare string literals).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.audit.models import GUID
from app.infra.db.base import Base

__all__ = ["AccountCategory", "AccountCode", "ActualExpense"]


def _category_values(enum_cls: Any) -> list[str]:
    """Return the list of values used by the Postgres ``account_category`` enum.

    Args:
        enum_cls: The :class:`AccountCategory` class.

    Returns:
        list[str]: Each member's raw string value in declaration order.
    """
    return [member.value for member in enum_cls]


class AccountCategory(StrEnum):
    """Closed vocabulary for account categories (CR-020 owner).

    Values MUST stay lowercase and match the Postgres ``account_category``
    enum declared in the Alembic baseline. Downstream services compare
    against these members directly — never use the string literals.
    """

    operational = "operational"
    personnel = "personnel"
    shared_cost = "shared_cost"


class AccountCode(Base):
    """ORM mapping for the ``account_codes`` table (FR-007).

    The ``code`` column is the natural key used by
    :meth:`app.domain.accounts.service.AccountService.upsert`. ``category``
    is a PostgreSQL enum backed by :class:`AccountCategory`; the
    ``values_callable`` shim keeps the values lowercase on SQLite too.
    """

    __tablename__ = "account_codes"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[AccountCategory] = mapped_column(
        SAEnum(
            AccountCategory,
            name="account_category",
            values_callable=_category_values,
            native_enum=True,
            create_type=False,
        ),
        nullable=False,
    )
    level: Mapped[int] = mapped_column(Integer(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=None
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=None
    )


class ActualExpense(Base):
    """ORM mapping for the ``actual_expenses`` table (FR-008).

    Primary key is ``id``; the business uniqueness is enforced by the
    composite ``(cycle_id, org_unit_id, account_code_id)`` unique index
    declared in the Alembic baseline, so
    :meth:`AccountService.import_actuals` uses delete-then-insert per
    ``cycle_id`` for atomic replacement semantics.
    """

    __tablename__ = "actual_expenses"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    cycle_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("budget_cycles.id"),
        nullable=False,
    )
    org_unit_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("org_units.id"),
        nullable=False,
    )
    account_code_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("account_codes.id"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=None
    )
    imported_by: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=None
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=None
    )
