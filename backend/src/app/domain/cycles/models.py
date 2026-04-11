"""ORM models + state enum for :mod:`app.domain.cycles`.

Maps the ``budget_cycles`` and ``cycle_reminder_schedules`` tables defined
in ``alembic/versions/0001_baseline.py``. :class:`OrgUnit` is intentionally
re-exported from :mod:`app.core.security.models` — Batch 2 already shipped
the canonical ORM mapping there (with ``excluded_for_cycle_ids`` per the
0002 migration), so this module imports it instead of re-declaring the
class. The decision keeps a single source of truth for the ``org_units``
table and avoids SQLAlchemy mapper conflicts when both packages are
imported by the same process.

The :class:`CycleState` enum follows the CR-020 StrEnum pattern: the SQL
comparison passes the raw enum value, so checks like ``cycle.status ==
CycleState.open`` compare native ``str`` values correctly regardless of
whether the backing dialect is Postgres (native enum) or SQLite (TEXT).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CHAR, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.security.models import OrgUnit
from app.domain.audit.models import GUID
from app.infra.db.base import Base

__all__ = [
    "BudgetCycle",
    "CycleReminderSchedule",
    "CycleState",
    "OrgUnit",
]


class CycleState(StrEnum):
    """Lifecycle states of a :class:`BudgetCycle`.

    The three members map to the Postgres ``cycle_status`` enum defined in
    the Alembic baseline (``draft``, ``open``, ``closed``). The StrEnum
    subclass ensures SQL comparisons serialize the raw value.
    """

    draft = "draft"
    open = "open"
    closed = "closed"


class BudgetCycle(Base):
    """ORM mapping for the ``budget_cycles`` table.

    Mirrors the DDL in ``alembic/versions/0001_baseline.py`` column for
    column. ``status`` is stored as a string (mapped from :class:`CycleState`)
    so the same column works against Postgres (``cycle_status`` enum) and
    SQLite (TEXT) in the unit-test tier.
    """

    __tablename__ = "budget_cycles"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    fiscal_year: Mapped[int] = mapped_column(Integer(), nullable=False)
    deadline: Mapped[date] = mapped_column(Date(), nullable=False)
    reporting_currency: Mapped[str] = mapped_column(
        CHAR(3),
        nullable=False,
        default="TWD",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=CycleState.draft.value,
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[UUID | None] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=True,
    )
    reopen_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class CycleReminderSchedule(Base):
    """ORM mapping for the ``cycle_reminder_schedules`` table."""

    __tablename__ = "cycle_reminder_schedules"
    __table_args__ = (CheckConstraint("days_before > 0", name="cycle_reminder_days_positive"),)

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    cycle_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("budget_cycles.id", ondelete="CASCADE"),
        nullable=False,
    )
    days_before: Mapped[int] = mapped_column(Integer(), nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
