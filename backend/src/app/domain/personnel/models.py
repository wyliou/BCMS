"""SQLAlchemy ORM models for ``personnel_budget_uploads`` and
``personnel_budget_lines`` tables (FR-024, FR-025).

Mirrors the Alembic baseline column-for-column so the ORM round-trips
cleanly against both the real Postgres schema and the portable
unit-test engine.

The baseline enforces the ``(cycle_id, version)`` UNIQUE constraint
that guards concurrent version monotonicity (CR-025) — personnel imports
are company-wide, so versioning is per-cycle rather than per-org-unit.
``personnel_budget_lines`` has an ``amount > 0`` CHECK constraint (CR-012).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.domain.audit.models import GUID
from app.infra.db.base import Base

__all__ = ["PersonnelBudgetUpload", "PersonnelBudgetLine"]


class PersonnelBudgetUpload(Base):
    """ORM mapping for the ``personnel_budget_uploads`` table (FR-025).

    Each row represents a single versioned personnel budget import for a
    cycle. The ``version`` column is a monotonic integer allocated via
    :func:`app.infra.db.helpers.next_version` inside the persisting
    transaction (CR-025); versioning is per-cycle (not per-org-unit).

    Attributes:
        id: Primary key UUID.
        cycle_id: FK → ``budget_cycles.id``.
        uploader_user_id: FK → ``users.id``.
        uploaded_at: UTC timestamp of the successful import.
        filename: Original client-supplied filename.
        file_hash: Opaque storage key returned by :func:`infra.storage.save`.
        version: Monotonic version integer per ``cycle_id``.
        affected_org_units_summary: JSONB snapshot of affected units and totals.
    """

    __tablename__ = "personnel_budget_uploads"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    cycle_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("budget_cycles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uploader_user_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer(), nullable=False)
    affected_org_units_summary: Mapped[Any] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )


class PersonnelBudgetLine(Base):
    """ORM mapping for the ``personnel_budget_lines`` table (FR-024).

    Each row is a single org-unit + account-code amount associated with a
    :class:`PersonnelBudgetUpload`. The baseline CHECK constraint enforces
    ``amount > 0`` at the DB layer (CR-012 — personnel amounts must be
    strictly positive).

    Attributes:
        id: Primary key UUID.
        upload_id: FK → ``personnel_budget_uploads.id`` (cascade delete).
        org_unit_id: FK → ``org_units.id``.
        account_code_id: FK → ``account_codes.id``.
        amount: Strictly positive :class:`Decimal` quantized to ``0.01``.
    """

    __tablename__ = "personnel_budget_lines"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    upload_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("personnel_budget_uploads.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_unit_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("org_units.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_code_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("account_codes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
