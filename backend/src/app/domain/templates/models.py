"""SQLAlchemy ORM model for the ``excel_templates`` table (FR-009, FR-010).

Mirrors ``alembic/versions/0001_baseline.py`` column-for-column. The
``file_path`` column is AES-GCM encrypted at the service layer (via
:func:`app.infra.crypto.encrypt_field` / :func:`decrypt_field`) and
persisted as ``file_path_enc`` ``LargeBinary``. The service translates
between the opaque :mod:`app.infra.storage` key (plaintext) and the
ciphertext blob.

The logical ``status`` is derived from the presence of
``generation_error``: when the column is ``NULL`` the template is
``generated``, otherwise it is in the ``error`` state. The baseline
schema has no dedicated ``status`` column, so this module exposes the
derived value via :meth:`ExcelTemplate.status` rather than a real
mapped column.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.audit.models import GUID
from app.infra.db.base import Base

__all__ = ["ExcelTemplate", "TemplateStatus"]


class TemplateStatus(StrEnum):
    """Logical status of an :class:`ExcelTemplate` row.

    Values:
        generated: The workbook was built and persisted successfully.
        error: Generation failed; ``generation_error`` carries the reason.
    """

    generated = "generated"
    error = "error"


class ExcelTemplate(Base):
    """ORM mapping for the ``excel_templates`` table.

    Mirrors the Alembic baseline DDL verbatim. Uniqueness of
    ``(cycle_id, org_unit_id)`` is enforced by the baseline
    ``uq_templates_cycle_org`` constraint — the service performs a
    delete-then-insert upsert for regenerate semantics.

    Attributes:
        id: Primary key (random UUID).
        cycle_id: Foreign key → ``budget_cycles.id``.
        org_unit_id: Foreign key → ``org_units.id``.
        file_path_enc: AES-GCM ciphertext of the opaque storage key
            returned by :mod:`app.infra.storage`. The service uses
            :func:`encrypt_field` / :func:`decrypt_field` to round-trip.
        file_hash: SHA-256 digest of the stored bytes (32 bytes).
        generated_at: Timestamp when the row was last (re)generated.
        generated_by: Foreign key → ``users.id``.
        download_count: Monotonically increments per successful
            download (FR-010).
        generation_error: Nullable error message when ``status`` is
            :attr:`TemplateStatus.error`.
    """

    __tablename__ = "excel_templates"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    cycle_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("budget_cycles.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_unit_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("org_units.id", ondelete="RESTRICT"),
        nullable=False,
    )
    file_path_enc: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    file_hash: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    generated_by: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False,
    )
    download_count: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=0,
    )
    generation_error: Mapped[str | None] = mapped_column(Text(), nullable=True)

    @property
    def status(self) -> TemplateStatus:
        """Return the derived logical status.

        Returns:
            TemplateStatus: :attr:`TemplateStatus.error` when
            :attr:`generation_error` is set, else
            :attr:`TemplateStatus.generated`.
        """
        if self.generation_error is not None:
            return TemplateStatus.error
        return TemplateStatus.generated
