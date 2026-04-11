"""FastAPI routes for SSO login / refresh / logout / whoami (M10).

Thin orchestration — every piece of business logic lives in
:class:`app.core.security.auth_service.AuthService`. The router handles
cookie plumbing and the redirect dance with the IdP.

CR-032 note: ``GET /auth/me`` reads the authenticated user via
:meth:`AuthService.current_user`, which raises ``AUTH_002`` on any
failure (the global exception handler maps that to 401). The login
and callback routes are explicitly unauthenticated — they do not
carry an RBAC dependency because there is no principal yet.
"""

from __future__ import annotations

from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import UnauthenticatedError
from app.core.security.auth_service import (
    REFRESH_COOKIE_NAME,
    AuthService,
)
from app.core.security.cookies import clear_session_cookies, set_session_cookies
from app.core.security.models import User
from app.infra.db.session import get_session
from app.infra.sso import OIDCClient, SSOClient

__all__ = ["router", "WhoAmIResponse", "get_sso_client"]


router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def get_sso_client() -> SSOClient:
    """FastAPI dependency that returns the active :class:`SSOClient`.

    Tests override this via ``app.dependency_overrides[get_sso_client]``
    to inject :class:`~app.infra.sso.FakeSSO`.

    Returns:
        SSOClient: Production :class:`OIDCClient`, or a fake during tests.
    """
    return OIDCClient()


async def _service(
    db: AsyncSession = Depends(get_session),
    sso: SSOClient = Depends(get_sso_client),
) -> AuthService:
    """Construct an :class:`AuthService` from request-scoped dependencies.

    Args:
        db (AsyncSession): DB session from :func:`get_session`.
        sso (SSOClient): SSO client from :func:`get_sso_client`.

    Returns:
        AuthService: Service instance bound to the request.
    """
    return AuthService(db, sso_client=sso)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class WhoAmIResponse(BaseModel):
    """Body returned by ``GET /auth/me``.

    Attributes:
        user_id (UUID): Authenticated user id.
        role (str | None): Primary role value.
        roles (list[str]): Every role the user holds.
        org_unit_id (UUID | None): Scoped org unit id.
        display_name (str): Human-readable display name.
    """

    user_id: UUID
    role: str | None
    roles: list[str]
    org_unit_id: UUID | None
    display_name: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/sso/login")
async def sso_login(return_to: str = Query(default="/")) -> RedirectResponse:
    """Redirect to the IdP authorization endpoint.

    Args:
        return_to (str): Path to redirect to after successful login.

    Returns:
        RedirectResponse: 302 redirect carrying the IdP authorization
        URL in the ``Location`` header.
    """
    settings = get_settings()
    base = settings.sso_issuer or settings.sso_discovery_url or ""
    params = {
        "client_id": settings.sso_client_id,
        "redirect_uri": settings.sso_redirect_uri,
        "response_type": "code",
        "scope": settings.sso_scopes,
        "state": return_to,
    }
    if base:
        url = f"{base.rstrip('/')}/authorize?{urlencode(params)}"
    else:
        # Reason: local/dev installs without a real IdP still want the
        # route to return a deterministic 302 so integration smoke tests
        # don't blow up; the URL points at the app's own callback.
        url = f"{settings.api_base_url}/api/v1/auth/sso/callback?{urlencode(params)}"
    return RedirectResponse(url=url, status_code=302)


@router.get("/sso/callback")
async def sso_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(default="/"),
    service: AuthService = Depends(_service),
) -> Response:
    """Exchange the SSO code for session cookies and redirect.

    Args:
        request (Request): Inbound request (for IP / User-Agent).
        code (str): Authorization code from the IdP.
        state (str): Return path originally passed to ``/sso/login``.
        service (AuthService): Injected auth service.

    Returns:
        Response: 302 redirect to ``state`` with the three session
        cookies attached.
    """
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    tokens = await service.handle_sso_callback(
        provider=get_settings().sso_provider,
        payload={"code": code},
        ip=ip,
        user_agent=user_agent,
    )
    frontend = get_settings().frontend_origin
    target = f"{frontend.rstrip('/')}{state or '/'}" if frontend else state or "/"
    response = RedirectResponse(url=target, status_code=302)
    set_session_cookies(response, tokens)
    return response


@router.post("/refresh")
async def refresh(
    request: Request,
    service: AuthService = Depends(_service),
) -> Response:
    """Rotate the session using the ``bc_refresh`` cookie.

    Args:
        request (Request): Inbound request carrying the refresh cookie.
        service (AuthService): Injected auth service.

    Returns:
        Response: Empty 204 with fresh cookies attached.

    Raises:
        UnauthenticatedError: ``AUTH_002`` if the refresh cookie is
            missing, expired, or already revoked.
    """
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw:
        raise UnauthenticatedError("AUTH_002", "Refresh cookie missing")
    tokens = await service.refresh_session(raw)
    response = Response(status_code=204)
    set_session_cookies(response, tokens)
    return response


@router.post("/logout")
async def logout(
    request: Request,
    service: AuthService = Depends(_service),
) -> Response:
    """Revoke the current session and clear the cookies.

    Args:
        request (Request): Inbound request carrying cookies.
        service (AuthService): Injected auth service.

    Returns:
        Response: Empty 204 with cookies cleared.
    """
    try:
        user = await service.current_user(request)
    except UnauthenticatedError:
        response = Response(status_code=204)
        clear_session_cookies(response)
        return response

    # Reason: in Batch 2 we do not persist the session_id alongside the
    # JWT claims, so logout revokes every active session for the user.
    from sqlalchemy import select

    from app.core.security.models import Session as SessionRow

    stmt = select(SessionRow).where(
        SessionRow.user_id == user.id,
        SessionRow.revoked_at.is_(None),
    )
    result = await service._db.execute(stmt)
    for row in result.scalars().all():
        await service.logout(row.id)

    response = Response(status_code=204)
    clear_session_cookies(response)
    return response


@router.get("/me", response_model=WhoAmIResponse)
async def whoami(
    request: Request,
    service: AuthService = Depends(_service),
) -> WhoAmIResponse:
    """Return a summary of the authenticated user.

    Args:
        request (Request): Inbound request carrying the session cookie.
        service (AuthService): Injected auth service.

    Returns:
        WhoAmIResponse: ``{user_id, role, roles, org_unit_id, display_name}``.

    Raises:
        UnauthenticatedError: ``AUTH_002`` when no active session
            cookie is present.
    """
    user: User = await service.current_user(request)
    return WhoAmIResponse(
        user_id=user.id,
        role=user.role.value if user.role is not None else None,
        roles=[r.value for r in user.role_set()],
        org_unit_id=user.org_unit_id,
        display_name=user.display_name,
    )
