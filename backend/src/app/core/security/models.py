"""SQLAlchemy ORM models for ``users``, ``sessions``, and ``org_units``.

Mirrors the Alembic baseline (``alembic/versions/0001_baseline.py``)
verbatim. The columns here match the baseline DDL column-for-column so
that the ORM round-trips cleanly against the real Postgres schema, plus a
single Batch-2 migration (``0002_org_unit_excluded_cycles``) which adds
the ``org_units.excluded_for_cycle_ids`` JSONB column that powers the
FR-002 per-cycle filing-unit exclusion decision.

Notes
-----
* ``users.roles`` is a JSONB array of :class:`app.core.security.roles.Role`
  values. The :attr:`User.role` helper returns the first member of that
  array as a convenience for downstream code that expects a single role;
  RBAC itself uses the whole list via :meth:`User.role_set`.
* The table is portable across Postgres (real) and SQLite (unit-test
  in-memory engine) via the same :class:`GUID` and :class:`JSONDict`
  type-decorators already used by the audit model — we re-import them
  here so this module does not re-declare them.
* ``refresh_token_hash`` is a 32-byte HMAC-SHA256 digest (produced by
  :func:`app.infra.crypto.hmac_lookup_hash`). No raw refresh token ever
  lives on disk.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.security.roles import Role
from app.domain.audit.models import GUID, JSONDict
from app.infra.db.base import Base

__all__ = ["User", "Session", "OrgUnit"]


class OrgUnit(Base):
    """ORM for the ``org_units`` table.

    Only the columns needed by RBAC and the admin ``PATCH /org-units``
    route are mapped — downstream batches (M1 cycles) may add helpers or
    relationships, but the column list MUST stay consistent with the
    baseline DDL plus the ``excluded_for_cycle_ids`` column added by the
    ``0002_org_unit_excluded_cycles`` migration.
    """

    __tablename__ = "org_units"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    level_code: Mapped[str] = mapped_column(String(8), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("org_units.id"), nullable=True
    )
    is_filing_unit: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    is_reviewer_only: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    excluded_for_cycle_ids: Mapped[list[str]] = mapped_column(
        JSONDict(),
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=None
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=None
    )


class User(Base):
    """ORM for the ``users`` table.

    ``email`` and ``sso_id`` are persisted as AES-GCM ciphertext in the
    ``*_enc`` columns; lookups use the HMAC hash columns (``*_hash``).
    The :attr:`role` convenience property returns the primary role from
    the JSONB ``roles`` array — consumers that need the full set call
    :meth:`role_set`.
    """

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    sso_id_enc: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    sso_id_hash: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email_enc: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False)
    email_hash: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False, unique=True)
    roles: Mapped[list[str]] = mapped_column(JSONDict(), nullable=False, default=list)
    org_unit_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("org_units.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=None
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=None
    )

    # ------------------------------------------------------------------
    @property
    def display_name(self) -> str:
        """Return the user's display name (alias for ``name``).

        Returns:
            str: The ``name`` column value.
        """
        return self.name

    @property
    def role(self) -> Role | None:
        """Return the primary :class:`Role` from ``roles`` JSONB array.

        Returns:
            Role | None: First mapped role, or ``None`` if the array is
            empty or contains only unknown strings.
        """
        raw_roles = self.roles or []
        for item in raw_roles:
            try:
                return Role(item)
            except ValueError:
                continue
        return None

    def role_set(self) -> set[Role]:
        """Return every known role from the JSONB ``roles`` array.

        Returns:
            set[Role]: All parseable :class:`Role` members in the array.
        """
        result: set[Role] = set()
        for item in self.roles or []:
            try:
                result.add(Role(item))
            except ValueError:
                continue
        return result


class Session(Base):
    """ORM for the ``sessions`` table.

    Fields follow the baseline DDL exactly:

    * ``refresh_token_hash`` — HMAC-SHA256 lookup digest for the raw
      refresh token (never the raw token itself).
    * ``csrf_token`` — the double-submit cookie token string issued with
      each session (also served via the ``bc_csrf`` cookie).
    * ``absolute_expires_at`` — hard absolute expiry independent of
      ``last_activity_at`` idle tracking.
    * ``revoked_at`` — set by :meth:`AuthService.logout` (never deleted).
    """

    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    refresh_token_hash: Mapped[bytes] = mapped_column(LargeBinary(), nullable=False, unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text(), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
