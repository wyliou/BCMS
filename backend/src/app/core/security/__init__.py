"""Core security package — SSO, JWT, RBAC, CSRF, sessions (M10).

See ``specs/core_security.md`` for the canonical contract. Submodules:

* :mod:`app.core.security.roles` — :class:`Role` and :class:`ResourceType` enums.
* :mod:`app.core.security.models` — :class:`User`, :class:`Session`, :class:`OrgUnit`.
* :mod:`app.core.security.jwt` — HS256 mint/verify helpers.
* :mod:`app.core.security.csrf` — double-submit CSRF helpers.
* :mod:`app.core.security.sessions` — session row CRUD + token bundle.
* :mod:`app.core.security.rbac` — ``require_role`` / ``require_scope`` / ``scoped_org_units``.
* :mod:`app.core.security.auth_service` — :class:`AuthService` high-level facade.
* :mod:`app.core.security.cookies` — cookie set/clear helpers for route handlers.
"""

from app.core.security.auth_service import AuthService
from app.core.security.cookies import clear_session_cookies, set_session_cookies
from app.core.security.csrf import issue_csrf_token, verify_csrf, verify_csrf_token
from app.core.security.jwt import decode_access_token, encode_access_token
from app.core.security.models import OrgUnit, Session, User
from app.core.security.rbac import ALL_SCOPES, require_role, require_scope, scoped_org_units
from app.core.security.roles import ResourceType, Role
from app.core.security.sessions import SessionStore, SessionTokens

__all__ = [
    "ALL_SCOPES",
    "AuthService",
    "OrgUnit",
    "ResourceType",
    "Role",
    "Session",
    "SessionStore",
    "SessionTokens",
    "User",
    "clear_session_cookies",
    "decode_access_token",
    "encode_access_token",
    "issue_csrf_token",
    "require_role",
    "require_scope",
    "scoped_org_units",
    "set_session_cookies",
    "verify_csrf",
    "verify_csrf_token",
]
