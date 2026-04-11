"""SQLAlchemy ORM model for the ``audit_logs`` table.

Mirrors the Alembic baseline DDL (``alembic/versions/0001_baseline.py``)
exactly. The table is append-only at the DB layer — the baseline migration
runs ``REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC`` after creation —
so this ORM model intentionally exposes no update-helper methods and omits
an ``updated_at`` column. Rows are inserted exclusively via
:class:`app.domain.audit.service.AuditService.record`.

Column choices are chosen so the model works against both production
PostgreSQL and an in-memory SQLite engine used by unit tests: dialect
differences (``postgresql.UUID`` vs ``CHAR(36)``) are handled via the
``as_uuid`` SQLAlchemy type where available and fall back to generic types
on SQLite.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, LargeBinary, String
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import CHAR, JSON, TypeDecorator

from app.infra.db.base import Base

__all__ = ["AuditLog", "GUID", "JSONDict"]


class GUID(TypeDecorator[UUID]):
    """Platform-independent UUID type.

    Uses PostgreSQL's ``UUID`` type when available, falls back to ``CHAR(36)``
    on other backends (notably SQLite used in the unit-test tier). This keeps
    :class:`AuditLog` portable across the production Postgres engine and the
    in-memory test engine without requiring dialect-specific imports at model
    definition time.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        """Bind the dialect-specific column type.

        Args:
            dialect: Active SQLAlchemy dialect.

        Returns:
            TypeEngine: ``UUID`` on Postgres, ``CHAR(36)`` otherwise.
        """
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        """Serialize a Python value for the DB column.

        Args:
            value: The UUID (or ``None``) being stored.
            dialect: Active SQLAlchemy dialect.

        Returns:
            object: UUID object for Postgres, string otherwise; ``None`` passes through.
        """
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, UUID) else UUID(str(value))
        return str(value) if isinstance(value, UUID) else str(UUID(str(value)))

    def process_result_value(self, value: Any, dialect: Any) -> UUID | None:
        """Deserialize a DB value back to a :class:`uuid.UUID`.

        Args:
            value: Raw column value from the driver.
            dialect: Active SQLAlchemy dialect.

        Returns:
            UUID | None: Parsed UUID, or ``None`` when the column was NULL.
        """
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        return UUID(str(value))


class JSONDict(TypeDecorator[dict[str, Any]]):
    """Portable JSON column type.

    Uses PostgreSQL ``JSONB`` when available; otherwise falls back to the
    generic SQLAlchemy :class:`~sqlalchemy.types.JSON` type (which SQLite
    stores as TEXT). Ensures the unit-test tier can round-trip ``details``
    dicts without requiring Postgres.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        """Bind the dialect-specific JSON column type.

        Args:
            dialect: Active SQLAlchemy dialect.

        Returns:
            TypeEngine: ``JSONB`` on Postgres, generic ``JSON`` otherwise.
        """
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class _INETString(TypeDecorator[str]):
    """Portable INET column type.

    Uses PostgreSQL ``INET`` on Postgres, ``VARCHAR(64)`` elsewhere. Stored
    and loaded as a plain Python ``str`` in either case — the model reads
    and writes ``str | None``.
    """

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        """Bind the dialect-specific INET column type.

        Args:
            dialect: Active SQLAlchemy dialect.

        Returns:
            TypeEngine: ``INET`` on Postgres, ``VARCHAR(64)`` otherwise.
        """
        if dialect.name == "postgresql":
            return dialect.type_descriptor(INET())
        return dialect.type_descriptor(String(64))


class AuditLog(Base):
    """SQLAlchemy ORM for the ``audit_logs`` table.

    Append-only. The ORM does not prevent update/delete — the DB-level
    ``REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC`` applied by the
    Alembic baseline does. Application code must only call
    :meth:`app.domain.audit.service.AuditService.record` to write rows;
    this model intentionally provides no mutation helpers.

    Columns mirror architecture §6 / the baseline DDL exactly. Of note:

    * ``sequence_no`` uses ``BIGSERIAL`` semantics (autoincrement + unique).
      The DB assigns the value on INSERT; application code never sets it.
    * ``prev_hash`` is ``NOT NULL`` — the very first row uses the 32-byte
      zero sentinel (``b"\\x00" * 32``) rather than ``NULL``.
    * ``details`` defaults to the empty JSON object at the DB layer.
    * ``occurred_at`` is server-defaulted to ``NOW()``; the service passes
      an explicit UTC timestamp so it matches the chain payload.
    """

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid4,
    )
    sequence_no: Mapped[int] = mapped_column(
        BigInteger(),
        unique=True,
        autoincrement=True,
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        GUID(),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    resource_id: Mapped[UUID | None] = mapped_column(
        GUID(),
        nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(
        _INETString(),
        nullable=True,
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONDict(),
        nullable=False,
        default=dict,
    )
    prev_hash: Mapped[bytes] = mapped_column(
        LargeBinary(),
        nullable=False,
    )
    hash_chain_value: Mapped[bytes] = mapped_column(
        LargeBinary(),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
