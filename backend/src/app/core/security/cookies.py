"""HTTP cookie helpers for session transport (FR-021, architecture §3).

Three cookies are used::

    bc_session  HttpOnly, Secure, SameSite=lax,    path=/
    bc_refresh  HttpOnly, Secure, SameSite=strict, path=/api/v1/auth
    bc_csrf     Secure (NOT HttpOnly),             path=/

The ``bc_csrf`` cookie is intentionally readable by JavaScript so the
SPA can echo it back in the ``X-CSRF-Token`` header on state-changing
requests (double-submit pattern — see
:mod:`app.core.security.csrf`).
"""

from __future__ import annotations

from fastapi import Response

from app.config import get_settings
from app.core.security.auth_service import REFRESH_COOKIE_NAME, SESSION_COOKIE_NAME
from app.core.security.csrf import CSRF_COOKIE_NAME
from app.core.security.sessions import SessionTokens

__all__ = ["set_session_cookies", "clear_session_cookies"]


_REFRESH_COOKIE_PATH = "/api/v1/auth"


def set_session_cookies(response: Response, tokens: SessionTokens) -> None:
    """Attach all three session cookies to the outbound response.

    Args:
        response (Response): FastAPI/Starlette response to mutate.
        tokens (SessionTokens): Newly minted token bundle.
    """
    settings = get_settings()
    secure = bool(settings.cookie_secure)
    domain = settings.cookie_domain or None

    response.set_cookie(
        SESSION_COOKIE_NAME,
        tokens.access_token,
        max_age=int(settings.session_ttl_seconds),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        domain=domain,
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        tokens.refresh_token,
        max_age=int(settings.refresh_ttl_seconds),
        httponly=True,
        secure=secure,
        samesite="strict",
        path=_REFRESH_COOKIE_PATH,
        domain=domain,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        tokens.csrf_token,
        max_age=int(settings.refresh_ttl_seconds),
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
        domain=domain,
    )


def clear_session_cookies(response: Response) -> None:
    """Delete all three session cookies on ``response``.

    Args:
        response (Response): FastAPI/Starlette response to mutate.
    """
    settings = get_settings()
    domain = settings.cookie_domain or None
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", domain=domain)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=_REFRESH_COOKIE_PATH, domain=domain)
    response.delete_cookie(CSRF_COOKIE_NAME, path="/", domain=domain)
