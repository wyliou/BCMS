"""Double-submit CSRF token helpers.

The double-submit pattern works as follows:

1. On login, the server issues a random token in the ``bc_csrf`` cookie
   (NOT ``HttpOnly`` — the SPA reads it via ``document.cookie``).
2. For every state-changing request the SPA re-sends the value in the
   ``X-CSRF-Token`` header.
3. The server compares the header value to the cookie value with
   :func:`hmac.compare_digest` (constant-time).

The token itself is 32 random bytes hex-encoded (64 chars). It does NOT
carry state — it's opaque — and it's rotated on every session refresh.

This module exposes three helpers:

* :func:`issue_csrf_token` — generate a fresh token.
* :func:`generate_csrf_token` — spec alias kept for readability.
* :func:`verify_csrf` — compare cookie and header; raise
  :class:`ForbiddenError` with code ``RBAC_001`` on mismatch.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import Request

from app.core.errors import ForbiddenError

__all__ = [
    "issue_csrf_token",
    "generate_csrf_token",
    "verify_csrf",
    "verify_csrf_token",
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "CSRF_PROTECTED_METHODS",
]


CSRF_COOKIE_NAME = "bc_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_PROTECTED_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def issue_csrf_token() -> str:
    """Generate a fresh cryptographically-random CSRF token.

    Returns:
        str: 64-character hex string (32 bytes of randomness).
    """
    return secrets.token_hex(32)


def generate_csrf_token() -> str:
    """Alias for :func:`issue_csrf_token` kept to match the M10 spec wording.

    Returns:
        str: 64-character hex string.
    """
    return issue_csrf_token()


def verify_csrf_token(cookie_value: str | None, header_value: str | None) -> None:
    """Compare cookie and header tokens in constant time.

    Args:
        cookie_value: Value from the ``bc_csrf`` cookie.
        header_value: Value from the ``X-CSRF-Token`` request header.

    Raises:
        ForbiddenError: ``RBAC_001`` when either value is missing or the
            two do not match byte-for-byte.
    """
    if not cookie_value or not header_value:
        raise ForbiddenError("RBAC_001", "CSRF token missing")
    if not hmac.compare_digest(cookie_value, header_value):
        raise ForbiddenError("RBAC_001", "CSRF token mismatch")


def verify_csrf(request: Request, cookie_value: str | None = None) -> None:
    """Verify the CSRF double-submit pair on a FastAPI request.

    Only enforced for state-changing methods (see
    :data:`CSRF_PROTECTED_METHODS`). For ``GET``/``HEAD``/``OPTIONS`` the
    function returns silently.

    Args:
        request: Incoming FastAPI :class:`~fastapi.Request`.
        cookie_value: Optional override for the cookie value; when
            ``None`` the value is read from ``request.cookies``.

    Raises:
        ForbiddenError: ``RBAC_001`` on cookie/header mismatch.
    """
    if request.method.upper() not in CSRF_PROTECTED_METHODS:
        return
    cookie = cookie_value if cookie_value is not None else request.cookies.get(CSRF_COOKIE_NAME)
    header = request.headers.get(CSRF_HEADER_NAME)
    verify_csrf_token(cookie, header)
