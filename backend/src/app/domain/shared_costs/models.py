"""SQLAlchemy ORM models for ``shared_cost_uploads`` and ``shared_cost_lines`` tables.

Mirrors the Alembic baseline column-for-column. Each
:class:`SharedCostUpload` row represents one versioned import for a cycle.
The ``version`` is monotonic per ``cycle_id`` (global, not per org unit),
allocated via :func:`app.infra.db.helpers.next_version` (CR-025).

``affected_org_units_summary`` is a JSONB column that stores the per-import
diff metadata: ``unit_count``, ``unit_codes``, and ``diff_changed`` count.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.audit.models import GUID, JSONDict
from app.infra.db.base import Base

__all__ = ["SharedCostUpload", "SharedCostLine"]


class SharedCostUpload(Base):
    """ORM mapping for the ``shared_cost_uploads`` table (FR-027, FR-028).

    Each row is one successful shared cost import version for a cycle.
    The UNIQUE constraint ``uq_shared_cost_uploads_cycle_version`` (on
    ``cycle_id, version``) is the safety net for concurrent inserts.

    Attributes:
        id: Primary key UUID.
        cycle_id: FK → ``budget_cycles.id``.
        uploader_user_id: FK → ``users.id``.
        uploaded_at: UTC timestamp when the row was committed.
        filename: Original filename supplied by the client.
        file_hash: Raw SHA-256 digest of the uploaded bytes (32 bytes).
        version: Monotonic version integer per ``cycle_id``.
        affected_org_units_summary: JSONB dict with diff metadata.
    """

    __tablename__ = "shared_cost_uploads"

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
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    version: Mapped[int] = mapped_column(Integer(), nullable=False)
    affected_org_units_summary: Mapped[dict[str, object]] = mapped_column(
        JSONDict(),
        nullable=False,
        default=dict,
    )


class SharedCostLine(Base):
    """ORM mapping for the ``shared_cost_lines`` table (FR-027).

    Each row is one (org_unit, account_code, amount) triple associated
    with a :class:`SharedCostUpload`. The DB CHECK constraint enforces
    ``amount > 0`` (CR-012 — shared cost amounts must be strictly positive).

    Attributes:
        id: Primary key UUID.
        upload_id: FK → ``shared_cost_uploads.id`` (cascade delete).
        org_unit_id: FK → ``org_units.id``.
        account_code_id: FK → ``account_codes.id``.
        amount: Strictly positive :class:`Decimal` quantized to ``0.01``.
    """

    __tablename__ = "shared_cost_lines"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    upload_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("shared_cost_uploads.id", ondelete="CASCADE"),
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
