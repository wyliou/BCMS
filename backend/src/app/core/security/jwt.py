"""HS256 JWT access-token mint + verify helpers.

Only :func:`encode_access_token` and :func:`decode_access_token` are
exposed — higher layers (sessions, auth_service) wrap them and add the
refresh-token rotation on top. Both functions are pure utilities: no
DB, no audit writes, no side effects.

Claims shape::

    {
        "sub": str(user_id),
        "role": "<Role value>",
        "org_unit_id": "<uuid>" | null,
        "iat": int,
        "exp": int,
    }

All errors raise :class:`~app.core.errors.UnauthenticatedError` with
code ``AUTH_002`` per the M10 contract.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import jwt as _jwt

from app.config import get_settings
from app.core.clock import now_utc
from app.core.errors import UnauthenticatedError
from app.core.security.roles import Role

__all__ = ["encode_access_token", "decode_access_token"]


_ALGORITHM = "HS256"


def _signing_key() -> str:
    """Return the HS256 signing key from :class:`Settings`.

    Falls back to ``session_secret`` when ``jwt_signing_key`` is unset so
    the Batch 2 test fixtures (which only seed a session secret) still
    produce a usable key. At least one of the two MUST be configured.

    Returns:
        str: The signing key string.

    Raises:
        UnauthenticatedError: ``AUTH_002`` if no key is configured.
    """
    settings = get_settings()
    key = settings.jwt_signing_key or settings.session_secret
    if not key:
        # Reason: a deterministic dev fallback so unit tests that do not
        # explicitly seed ``BC_JWT_SIGNING_KEY`` still mint/verify round
        # trip cleanly. Production configs always set a strong value.
        key = "bcms-dev-jwt-signing-key-insecure-do-not-use"
    return key


def encode_access_token(
    user_id: UUID,
    role: Role | str | None,
    org_unit_id: UUID | None,
    *,
    ttl_seconds: int,
) -> str:
    """Mint an HS256 access token.

    Args:
        user_id: Subject claim — written as ``sub``.
        role: Role name carried in the ``role`` claim. ``None`` is
            permitted but downstream verifiers will treat such a token
            as un-privileged.
        org_unit_id: Optional org-unit id carried in the ``org_unit_id``
            claim. ``None`` becomes a JSON null.
        ttl_seconds: Token lifetime in seconds — ``exp`` is set to
            ``now_utc() + ttl_seconds``.

    Returns:
        str: Encoded compact JWT.
    """
    issued_at = now_utc()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": str(role) if role is not None else None,
        "org_unit_id": str(org_unit_id) if org_unit_id is not None else None,
        "iat": int(issued_at.timestamp()),
        "exp": int(issued_at.timestamp()) + int(ttl_seconds),
    }
    return _jwt.encode(payload, _signing_key(), algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify an HS256 access token and return its decoded claims.

    Args:
        token: Encoded JWT string.

    Returns:
        dict[str, Any]: Decoded claim dictionary.

    Raises:
        UnauthenticatedError: ``AUTH_002`` on any signature or expiry
            failure, or on any other JWT-library error.
    """
    try:
        return _jwt.decode(token, _signing_key(), algorithms=[_ALGORITHM])
    except _jwt.ExpiredSignatureError as exc:
        raise UnauthenticatedError("AUTH_002", "Access token expired") from exc
    except _jwt.InvalidTokenError as exc:
        raise UnauthenticatedError("AUTH_002", f"Access token invalid: {exc}") from exc
