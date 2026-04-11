"""High-level authentication service (SSO callback, refresh, logout, current_user).

Call order for :meth:`AuthService.handle_sso_callback` (verbatim from
``specs/core_security.md §4``)::

    1. SSOClient.exchange_code(code)          # InfraError on IdP failure
    2. SSOClient.fetch_userinfo(access_token) # InfraError on IdP failure
    3. Map raw_groups -> Role via settings.sso_role_mapping
       (AUTH_003 if no mapping matches; no DB writes yet)
    4. Upsert User row (keyed on hmac_lookup_hash(sso_id))
    5. SessionStore.create(...)               # writes Session row
    6. await db.commit()                      # state change committed
    7. encode_access_token(...) + compose SessionTokens
    8. AuditService.record(LOGIN_SUCCESS)     # CR-006 — AFTER commit
       (uses a fresh short-lived AsyncSession so an audit failure does
       not roll back the primary session write)
    9. return SessionTokens

Per CR-006, step 8 must follow step 6. If the audit write itself
raises, we re-raise so the caller can surface the failure — the session
row stays committed (audit is not inside the same transaction).

CR-006 side-session pattern
---------------------------

Every mutating method on :class:`AuthService` commits its primary
transaction first, then opens a **new** :class:`AsyncSession` from
:func:`app.infra.db.session.get_session_factory` to write the audit
row. This keeps the audit INSERT outside the caller's transaction
and matches the "audit AFTER commit, BEFORE return" invariant that
CR-006 enforces across the backend.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.clock import now_utc
from app.core.errors import InfraError, UnauthenticatedError
from app.core.security.jwt import decode_access_token
from app.core.security.models import User
from app.core.security.roles import Role
from app.core.security.sessions import SessionStore, SessionTokens
from app.domain.audit.actions import AuditAction
from app.domain.audit.service import AuditService
from app.infra.crypto import encrypt_field, hmac_lookup_hash
from app.infra.db.session import get_session_factory
from app.infra.sso import SSOClient, SSOUserInfo

__all__ = ["AuthService", "SESSION_COOKIE_NAME", "REFRESH_COOKIE_NAME"]


SESSION_COOKIE_NAME = "bc_session"
REFRESH_COOKIE_NAME = "bc_refresh"


class AuthService:
    """High-level authentication and session lifecycle service.

    Owns SSO callback processing, session refresh, logout, and
    :func:`current_user` resolution. Mutating methods follow the
    CR-006 commit-then-audit pattern: every state change commits the
    primary session first, then opens a short-lived side session to
    write the audit row.
    """

    def __init__(self, db: AsyncSession, sso_client: SSOClient | None = None) -> None:
        """Initialize with an active DB session and optional SSO client.

        Args:
            db (AsyncSession): Active async session (caller-managed).
            sso_client (SSOClient | None): Optional override (used by
                unit tests to inject ``FakeSSO``). Production callers
                pass the real :class:`app.infra.sso.OIDCClient`.
        """
        self._db = db
        self._sso = sso_client
        self._sessions = SessionStore(db)

    # ------------------------------------------------------------------
    # SSO callback
    # ------------------------------------------------------------------
    async def handle_sso_callback(
        self,
        provider: str,
        payload: dict[str, Any],
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> SessionTokens:
        """Exchange an SSO callback for a fresh session bundle.

        Args:
            provider (str): SSO provider identifier (e.g. ``"oidc"``).
            payload (dict[str, Any]): Callback payload; must contain
                at least a ``"code"`` key.
            ip (str | None): Request IP address for session telemetry.
            user_agent (str | None): Request User-Agent header.

        Returns:
            SessionTokens: Newly minted access / refresh / csrf tokens.

        Raises:
            InfraError: ``AUTH_001`` when the IdP is unreachable or
                returns a malformed response.
            UnauthenticatedError: ``AUTH_003`` when no role can be
                mapped from the user's raw groups.
        """
        del provider  # Reason: retained for API symmetry with spec.
        if self._sso is None:
            raise InfraError("AUTH_001", "SSO client not configured")

        code = payload.get("code")
        if not isinstance(code, str) or not code:
            raise InfraError("AUTH_001", "SSO callback missing 'code'")

        # Step 1–2: exchange + userinfo (may raise InfraError/AUTH_001).
        token_response = await self._sso.exchange_code(code)
        access_token = token_response.get("access_token")
        if not isinstance(access_token, str):
            raise InfraError("AUTH_001", "SSO token response missing access_token")
        raw_userinfo = await self._sso.fetch_userinfo(access_token)

        info = self._normalize_userinfo(raw_userinfo)

        # Step 3: map IdP groups -> Role (pre-DB).
        role = self._map_groups_to_role(info.raw_groups)
        if role is None:
            # AUTH_003 must audit even though no user row exists yet.
            await self._record_audit_side_session(
                action=AuditAction.AUTH_FAILED,
                resource_type="user",
                resource_id=None,
                user_id=None,
                ip_address=ip,
                details={"reason": "no_role_mapping", "sso_id": info.sso_id},
            )
            raise UnauthenticatedError("AUTH_003", "No role mapping for SSO subject")

        # Step 4: upsert User
        user = await self._upsert_user(info, role)

        # Step 5: create session row
        tokens = await self._sessions.create(user, ip=ip, user_agent=user_agent)

        # Step 6: commit primary transaction.
        await self._db.commit()

        # Step 7 already happened inside SessionStore.create.
        # Step 8: audit AFTER commit (CR-006).
        await self._record_audit_side_session(
            action=AuditAction.LOGIN_SUCCESS,
            resource_type="user",
            resource_id=user.id,
            user_id=user.id,
            ip_address=ip,
            details={"role": role.value, "session_id": str(tokens.session_id)},
        )
        return tokens

    # ------------------------------------------------------------------
    async def refresh_session(self, refresh_token: str) -> SessionTokens:
        """Rotate the given refresh token and return a new token bundle.

        Args:
            refresh_token (str): Raw refresh token from the
                ``bc_refresh`` cookie.

        Returns:
            SessionTokens: Newly minted bundle.

        Raises:
            UnauthenticatedError: ``AUTH_002`` when the token is not
                recognized, already revoked, or expired.
        """
        tokens = await self._sessions.refresh(refresh_token)
        await self._db.commit()
        await self._record_audit_side_session(
            action=AuditAction.LOGIN_SUCCESS,
            resource_type="session",
            resource_id=tokens.session_id,
            user_id=tokens.user_id,
            ip_address=None,
            details={"kind": "refresh"},
        )
        return tokens

    # ------------------------------------------------------------------
    async def logout(self, session_id: UUID) -> None:
        """Revoke the given session row and audit the logout.

        Args:
            session_id (UUID): ``sessions.id`` of the row to revoke.

        Raises:
            UnauthenticatedError: ``AUTH_002`` if the session is not
                found.
        """
        await self._sessions.revoke(session_id)
        await self._db.commit()
        await self._record_audit_side_session(
            action=AuditAction.LOGOUT,
            resource_type="session",
            resource_id=session_id,
            user_id=None,
            ip_address=None,
            details={},
        )

    # ------------------------------------------------------------------
    async def current_user(self, request: Request) -> User:
        """Resolve the authenticated user from the ``bc_session`` cookie.

        Args:
            request (Request): FastAPI request carrying cookies.

        Returns:
            User: Authenticated user with roles populated.

        Raises:
            UnauthenticatedError: ``AUTH_002`` on any failure to resolve
                the session (missing cookie, invalid JWT, missing user
                row, inactive user).
        """
        cookie = request.cookies.get(SESSION_COOKIE_NAME)
        if not cookie:
            raise UnauthenticatedError("AUTH_002", "Session cookie missing")
        claims = decode_access_token(cookie)
        sub = claims.get("sub")
        if not isinstance(sub, str):
            raise UnauthenticatedError("AUTH_002", "Session cookie missing 'sub'")
        try:
            user_id = UUID(sub)
        except ValueError as exc:
            raise UnauthenticatedError("AUTH_002", "Session cookie 'sub' not a UUID") from exc
        user = await self._db.get(User, user_id)
        if user is None:
            raise UnauthenticatedError("AUTH_002", "Session user not found")
        if not user.is_active:
            raise UnauthenticatedError("AUTH_002", "User is inactive")
        return user

    # ==================================================================
    # Internals
    # ==================================================================
    @staticmethod
    def _normalize_userinfo(raw: dict[str, Any]) -> SSOUserInfo:
        """Convert an IdP userinfo dict into :class:`SSOUserInfo`.

        Args:
            raw (dict[str, Any]): Raw IdP userinfo payload.

        Returns:
            SSOUserInfo: Normalized claims.

        Raises:
            InfraError: ``AUTH_001`` if required claims are missing.
        """
        sub = raw.get("sub")
        if not isinstance(sub, str) or not sub:
            raise InfraError("AUTH_001", "SSO userinfo missing 'sub'")
        email = raw.get("email")
        if not isinstance(email, str) or not email:
            raise InfraError("AUTH_001", "SSO userinfo missing 'email'")
        name = raw.get("name") or email.split("@", 1)[0]
        raw_groups: list[str] = []
        groups: object = raw.get("groups", [])
        if isinstance(groups, list):
            raw_groups = [str(g) for g in groups if isinstance(g, str)]  # pyright: ignore[reportUnknownVariableType]
        return SSOUserInfo(sso_id=sub, email=email, display_name=str(name), raw_groups=raw_groups)

    @staticmethod
    def _map_groups_to_role(raw_groups: list[str]) -> Role | None:
        """Return the first role that matches an entry in the mapping.

        Args:
            raw_groups (list[str]): Raw IdP group strings.

        Returns:
            Role | None: First matched role, or ``None`` if none match.
        """
        mapping = get_settings().sso_role_mapping or {}
        for group in raw_groups:
            role_name = mapping.get(group)
            if role_name is None:
                continue
            try:
                return Role(role_name)
            except ValueError:
                continue
        return None

    async def _upsert_user(self, info: SSOUserInfo, role: Role) -> User:
        """Upsert the ``users`` row keyed on ``sso_id_hash``.

        Args:
            info (SSOUserInfo): Normalized claims from the IdP.
            role (Role): Role mapped from ``info.raw_groups``.

        Returns:
            User: The freshly upserted (or updated-in-place) user row.
        """
        sso_hash = hmac_lookup_hash(info.sso_id.encode("utf-8"))
        stmt = select(User).where(User.sso_id_hash == sso_hash)
        result = await self._db.execute(stmt)
        user = result.scalars().first()

        now = now_utc()
        if user is None:
            user = User(
                sso_id_enc=encrypt_field(info.sso_id.encode("utf-8")),
                sso_id_hash=sso_hash,
                name=info.display_name,
                email_enc=encrypt_field(info.email.encode("utf-8")),
                email_hash=hmac_lookup_hash(info.email.encode("utf-8")),
                roles=[role.value],
                org_unit_id=None,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            self._db.add(user)
            await self._db.flush()
            return user

        # Update name / role / timestamps in place.
        user.name = info.display_name
        user.email_enc = encrypt_field(info.email.encode("utf-8"))
        user.email_hash = hmac_lookup_hash(info.email.encode("utf-8"))
        user.roles = [role.value]
        user.is_active = True
        user.updated_at = now
        await self._db.flush()
        return user

    @staticmethod
    async def _record_audit_side_session(
        *,
        action: AuditAction,
        resource_type: str,
        resource_id: UUID | None,
        user_id: UUID | None,
        ip_address: str | None,
        details: dict[str, Any],
    ) -> None:
        """Write an audit row on a fresh short-lived side session (CR-006).

        Per CR-006, audit rows must be written AFTER the primary
        transaction has committed. Using a side session ensures that
        audit failures cannot roll back the committed state change.

        Args:
            action (AuditAction): Closed enum member (CR-002).
            resource_type (str): Resource type label.
            resource_id (UUID | None): Target resource id.
            user_id (UUID | None): Actor id.
            ip_address (str | None): Request IP.
            details (dict[str, Any]): Event-specific metadata.
        """
        factory = get_session_factory()
        async with factory() as db:
            service = AuditService(db)
            await service.record(
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                user_id=user_id,
                ip_address=ip_address,
                details=details,
            )
            await db.commit()
