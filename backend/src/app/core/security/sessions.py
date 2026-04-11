"""Session store — create / refresh / revoke / get_active.

Transaction ownership
---------------------

This service never calls ``await db.commit()`` on the caller's behalf;
it exclusively uses ``await db.flush()`` so the caller can choose when
to commit. The higher-level :class:`AuthService` is responsible for the
commit sequencing required by CR-006 (commit state change first, then
audit write, then return).

Refresh-token storage
---------------------

A raw refresh token is a 32-byte random value returned to the client in
the ``bc_refresh`` cookie. On the server we persist only
:func:`app.infra.crypto.hmac_lookup_hash` of the raw token so equality
lookups don't require decryption. The raw token never touches the
database.

The baseline ``sessions`` table carries a dedicated ``csrf_token``
column (String(64)) — a fresh value is minted per session and returned
alongside the access/refresh tokens so that the route layer can issue
the ``bc_csrf`` cookie.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.clock import now_utc
from app.core.errors import UnauthenticatedError
from app.core.security.csrf import issue_csrf_token
from app.core.security.jwt import encode_access_token
from app.core.security.models import Session, User
from app.infra.crypto import hmac_lookup_hash

__all__ = ["SessionTokens", "SessionStore"]


class SessionTokens(BaseModel):
    """Bundle of freshly-minted tokens returned by :class:`SessionStore`.

    Attributes:
        access_token (str): HS256 JWT for the ``bc_session`` cookie.
        refresh_token (str): Opaque random token for the ``bc_refresh``
            cookie. Only the HMAC digest is stored server-side.
        csrf_token (str): Random token for the double-submit
            ``bc_csrf`` cookie.
        session_id (UUID): Primary key of the persisted ``sessions`` row.
        user_id (UUID): Authenticated user's id.
        expires_at (datetime): Absolute expiry of the session row.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    access_token: str
    refresh_token: str
    csrf_token: str
    session_id: UUID
    user_id: UUID
    expires_at: datetime


class SessionStore:
    """CRUD helper for the ``sessions`` table.

    All public methods return or accept Pydantic / ORM types; none of
    them commit on behalf of the caller. The ``AsyncSession`` passed to
    :meth:`__init__` is assumed to be managed by an outer
    :class:`AuthService` (or a test harness).
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an active :class:`AsyncSession`.

        Args:
            db (AsyncSession): Active async database session.
        """
        self._db = db

    # ------------------------------------------------------------------
    async def create(
        self,
        user: User,
        ip: str | None,
        user_agent: str | None,
    ) -> SessionTokens:
        """Create a new session row and return the minted tokens.

        Args:
            user (User): Authenticated user.
            ip (str | None): Remote IP captured from the request.
            user_agent (str | None): Remote User-Agent header value.

        Returns:
            SessionTokens: Bundle carrying the access / refresh / csrf
            tokens plus identifiers for the newly persisted row.
        """
        settings = get_settings()
        raw_refresh = secrets.token_urlsafe(32)
        refresh_hash = hmac_lookup_hash(raw_refresh.encode("utf-8"))
        csrf = issue_csrf_token()
        now = now_utc()
        expires = now + timedelta(seconds=int(settings.refresh_ttl_seconds))

        row = Session(
            user_id=user.id,
            refresh_token_hash=refresh_hash,
            csrf_token=csrf,
            ip_address=ip,
            user_agent=user_agent,
            last_activity_at=now,
            absolute_expires_at=expires,
            created_at=now,
            revoked_at=None,
        )
        self._db.add(row)
        await self._db.flush()

        access_token = encode_access_token(
            user.id,
            user.role,
            user.org_unit_id,
            ttl_seconds=int(settings.session_ttl_seconds),
        )
        return SessionTokens(
            access_token=access_token,
            refresh_token=raw_refresh,
            csrf_token=csrf,
            session_id=row.id,
            user_id=user.id,
            expires_at=expires,
        )

    # ------------------------------------------------------------------
    async def refresh(self, refresh_token: str) -> SessionTokens:
        """Rotate the session identified by ``refresh_token``.

        The lookup uses the HMAC digest — we never store the raw token.
        On success the old row is revoked and a new row is inserted with
        freshly minted access/refresh/csrf tokens. Both writes are
        flushed but NOT committed (the caller owns commit timing).

        Args:
            refresh_token (str): Raw refresh token from the
                ``bc_refresh`` cookie.

        Returns:
            SessionTokens: Newly minted token bundle.

        Raises:
            UnauthenticatedError: ``AUTH_002`` when no session matches,
                the row is already revoked, or it has expired.
        """
        digest = hmac_lookup_hash(refresh_token.encode("utf-8"))
        stmt = select(Session).where(Session.refresh_token_hash == digest)
        result = await self._db.execute(stmt)
        row = result.scalars().first()
        if row is None:
            raise UnauthenticatedError("AUTH_002", "Refresh token not found")
        if row.revoked_at is not None:
            raise UnauthenticatedError("AUTH_002", "Refresh token revoked")
        if row.absolute_expires_at <= now_utc():
            raise UnauthenticatedError("AUTH_002", "Refresh token expired")

        user = await self._db.get(User, row.user_id)
        if user is None or not user.is_active:
            raise UnauthenticatedError("AUTH_002", "User missing or inactive")

        # Revoke the old row and issue a new one.
        row.revoked_at = now_utc()
        await self._db.flush()
        return await self.create(user, ip=row.ip_address, user_agent=row.user_agent)

    # ------------------------------------------------------------------
    async def revoke(self, session_id: UUID) -> None:
        """Mark a session row as revoked.

        Args:
            session_id (UUID): Primary key of the ``sessions`` row.

        Raises:
            UnauthenticatedError: ``AUTH_002`` if no active session row
                exists for ``session_id``.
        """
        row = await self._db.get(Session, session_id)
        if row is None:
            raise UnauthenticatedError("AUTH_002", "Session not found")
        if row.revoked_at is None:
            row.revoked_at = now_utc()
            await self._db.flush()

    # ------------------------------------------------------------------
    async def get_active(self, session_id: UUID) -> Session | None:
        """Return the session row iff it exists, is not revoked, and not expired.

        Args:
            session_id (UUID): Primary key of the ``sessions`` row.

        Returns:
            Session | None: Active row or ``None`` if missing/revoked/expired.
        """
        row = await self._db.get(Session, session_id)
        if row is None:
            return None
        if row.revoked_at is not None:
            return None
        if row.absolute_expires_at <= now_utc():
            return None
        return row

    # ------------------------------------------------------------------
    async def touch(self, session_id: UUID) -> None:
        """Update ``last_activity_at`` on an active session.

        Args:
            session_id (UUID): Primary key of the session row.
        """
        row = await self._db.get(Session, session_id)
        if row is not None and row.revoked_at is None:
            row.last_activity_at = now_utc()
            await self._db.flush()
