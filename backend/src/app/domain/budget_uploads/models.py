"""SQLAlchemy ORM models for ``budget_uploads`` and ``budget_lines`` tables.

Mirrors the Alembic baseline (``alembic/versions/0001_baseline.py``)
column-for-column so the ORM round-trips cleanly against both the real
Postgres schema and the portable unit-test engine.

The baseline enforces the ``(cycle_id, org_unit_id, version)`` uniqueness
constraint that guards concurrent version monotonicity (CR-025), the
10 MB / 5000 row CHECK constraints owned by the DB, and the
``(upload_id, account_code_id)`` uniqueness on :class:`BudgetLine` that
makes delete-then-insert a no-op — callers always insert a fresh row per
upload version instead of upserting.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.audit.models import GUID
from app.infra.db.base import Base

__all__ = ["BudgetUpload", "BudgetLine", "UploadStatus"]


class UploadStatus(StrEnum):
    """Logical status of a :class:`BudgetUpload` row.

    The baseline Postgres ``upload_status`` enum has three values; the
    service layer only ever persists ``valid`` (successful uploads)
    because failed validations raise ``BatchValidationError`` before the
    persisting transaction opens (CR-004). The ``pending`` and
    ``invalid`` values are kept for symmetry with the baseline schema so
    the enum round-trips cleanly.
    """

    pending = "pending"
    valid = "valid"
    invalid = "invalid"


class BudgetUpload(Base):
    """ORM mapping for the ``budget_uploads`` table (FR-011, FR-012).

    Each row represents a single versioned budget upload for a
    ``(cycle_id, org_unit_id)`` pair. The ``version`` column is a
    monotonic integer allocated via :func:`app.infra.db.helpers.next_version`
    inside the persisting transaction (CR-025); the baseline UNIQUE
    constraint ``uq_budget_uploads_cycle_org_version`` is the final
    safety net for racing inserts.

    Attributes:
        id: Primary key UUID.
        cycle_id: FK → ``budget_cycles.id``.
        org_unit_id: FK → ``org_units.id``.
        uploader_id: FK → ``users.id``.
        version: Monotonic version integer per ``(cycle_id, org_unit_id)``.
        file_path_enc: AES-GCM ciphertext of the opaque storage key.
        file_hash: Raw SHA-256 digest of the uploaded bytes (32 bytes).
        file_size_bytes: Raw size of the upload in bytes.
        row_count: Parsed row count (after validation).
        status: :class:`UploadStatus` — always ``valid`` in practice.
        uploaded_at: Timestamp of the successful upload.
    """

    __tablename__ = "budget_uploads"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    cycle_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("budget_cycles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    org_unit_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("org_units.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uploader_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer(), nullable=False)
    file_path_enc: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    file_hash: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=UploadStatus.valid.value,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class BudgetLine(Base):
    """ORM mapping for the ``budget_lines`` table (FR-011).

    Each row is a single account-code amount associated with a
    :class:`BudgetUpload`. The baseline CHECK constraint
    ``budget_lines_amount_nonneg`` enforces ``amount >= 0`` at the DB
    layer (CR-012 — budget uploads accept zero as a valid amount).

    Attributes:
        id: Primary key UUID.
        upload_id: FK → ``budget_uploads.id`` (cascade delete).
        account_code_id: FK → ``account_codes.id``.
        amount: Non-negative :class:`Decimal` quantized to ``0.01``.
    """

    __tablename__ = "budget_lines"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    upload_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("budget_uploads.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_code_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("account_codes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
