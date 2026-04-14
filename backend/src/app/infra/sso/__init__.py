"""SSO adapter — :class:`SSOClient` :class:`Protocol` + Authlib OIDC implementation + fake double.

Role mapping is **out** of scope for this module. Callers in
``app.core.security`` translate raw IdP groups into system roles using
:attr:`Settings.sso_role_mapping`. This module is only concerned with the
IdP round-trip (authorization URL, token exchange, userinfo fetch).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx
import structlog

from app.config import Settings, get_settings
from app.core.errors import InfraError

__all__ = ["SSOUserInfo", "SSOClient", "OIDCClient", "FakeSSO"]


_LOG = structlog.get_logger(__name__)


@dataclass
class SSOUserInfo:
    """Normalized user profile returned by the IdP.

    Attributes:
        sso_id: Unique subject identifier from the IdP (``sub`` / NameID).
        email: User email address.
        display_name: Full name for display.
        raw_groups: Raw IdP group memberships (mapped to roles by security).
    """

    sso_id: str
    email: str
    display_name: str
    raw_groups: list[str] = field(default_factory=list)


@runtime_checkable
class SSOClient(Protocol):
    """Protocol implemented by real and fake SSO clients.

    Two concrete implementations satisfy this protocol: :class:`OIDCClient`
    (used in production) and :class:`FakeSSO` (used in unit tests).
    """

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange an authorization code for tokens (protocol method).

        Args:
            code: Authorization code from the callback query.

        Returns:
            dict[str, Any]: Raw token response.
        """
        return {}  # pragma: no cover — protocol contract

    async def fetch_userinfo(self, access_token: str) -> dict[str, Any]:
        """Fetch the userinfo claims given an access token (protocol method).

        Args:
            access_token: OAuth access token.

        Returns:
            dict[str, Any]: Raw userinfo claims dict.
        """
        return {}  # pragma: no cover — protocol contract


class OIDCClient:
    """Minimal Authlib-compatible OIDC client.

    Uses :mod:`httpx` directly for the token exchange and userinfo calls.
    Discovery is performed lazily on first use and cached.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the client from application settings.

        Args:
            settings: Optional pre-built :class:`Settings` instance. Defaults
                to :func:`get_settings`.
        """
        self._settings = settings or get_settings()
        self._metadata: dict[str, Any] | None = None

    async def _discover(self) -> dict[str, Any]:
        """Fetch and cache IdP OIDC metadata.

        Returns:
            dict[str, Any]: Parsed discovery document.

        Raises:
            InfraError: ``AUTH_001`` if the IdP is unreachable or returns a
                non-2xx response.
        """
        if self._metadata is not None:
            return self._metadata
        discovery_url = self._settings.sso_discovery_url
        if not discovery_url:
            raise InfraError("AUTH_001", "BC_SSO_DISCOVERY_URL not configured")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(discovery_url)
                response.raise_for_status()
                parsed = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise InfraError("AUTH_001", f"SSO discovery failed: {exc}") from exc
        if not isinstance(parsed, dict):
            raise InfraError("AUTH_001", "SSO discovery returned non-object payload")
        self._metadata = parsed
        return parsed

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange ``code`` for tokens at the IdP ``token_endpoint``.

        Args:
            code: Authorization code.

        Returns:
            dict[str, Any]: Token response body.

        Raises:
            InfraError: ``AUTH_001`` if the IdP is unreachable.
            InfraError: ``AUTH_002`` if the IdP returns 4xx (invalid code or
                state mismatch).
        """
        metadata = await self._discover()
        token_endpoint = metadata.get("token_endpoint")
        if not token_endpoint:
            raise InfraError("AUTH_001", "IdP metadata missing token_endpoint")
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self._settings.sso_client_id,
            "client_secret": self._settings.sso_client_secret or "",
            "redirect_uri": self._settings.sso_redirect_uri,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(token_endpoint, data=data)
        except httpx.HTTPError as exc:
            raise InfraError("AUTH_001", f"SSO token exchange transport error: {exc}") from exc
        if response.status_code >= 500:
            raise InfraError("AUTH_001", f"SSO token endpoint 5xx: {response.status_code}")
        if response.status_code >= 400:
            raise InfraError("AUTH_002", f"SSO token endpoint rejected: {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise InfraError("AUTH_002", "SSO token response is not JSON") from exc

    async def fetch_userinfo(self, access_token: str) -> dict[str, Any]:
        """Call the IdP userinfo endpoint.

        Args:
            access_token: Bearer access token.

        Returns:
            dict[str, Any]: Raw userinfo claims.

        Raises:
            InfraError: ``AUTH_001`` if the endpoint is unreachable.
        """
        metadata = await self._discover()
        userinfo_endpoint = metadata.get("userinfo_endpoint")
        if not userinfo_endpoint:
            raise InfraError("AUTH_001", "IdP metadata missing userinfo_endpoint")
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(userinfo_endpoint, headers=headers)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise InfraError("AUTH_001", f"SSO userinfo fetch failed: {exc}") from exc


@dataclass
class FakeSSO:
    """In-memory :class:`SSOClient` substitute for tests.

    Attributes:
        token_response: Payload returned from :meth:`exchange_code`.
        userinfo: Payload returned from :meth:`fetch_userinfo`.
        should_fail_auth_001: When ``True``, raise ``AUTH_001`` on exchange.
        should_fail_auth_002: When ``True``, raise ``AUTH_002`` on exchange.
    """

    token_response: dict[str, Any] = field(
        default_factory=lambda: {"access_token": "fake", "token_type": "Bearer"}
    )
    userinfo: dict[str, Any] = field(
        default_factory=lambda: {
            "sub": "user-1",
            "email": "user@example.invalid",
            "name": "Test User",
            "groups": ["BCMS_ADMIN"],
        }
    )
    should_fail_auth_001: bool = False
    should_fail_auth_002: bool = False

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Return the configured token response or raise a configured error.

        Args:
            code: Authorization code (ignored in the fake).

        Returns:
            dict[str, Any]: Fake token response.

        Raises:
            InfraError: ``AUTH_001`` or ``AUTH_002`` when configured to fail.
        """
        del code
        if self.should_fail_auth_001:
            raise InfraError("AUTH_001", "FakeSSO: IdP unreachable")
        if self.should_fail_auth_002:
            raise InfraError("AUTH_002", "FakeSSO: invalid state")
        return dict(self.token_response)

    async def fetch_userinfo(self, access_token: str) -> dict[str, Any]:
        """Return the configured userinfo claims.

        Args:
            access_token: Access token (ignored in the fake).

        Returns:
            dict[str, Any]: Fake userinfo dict.
        """
        del access_token
        return dict(self.userinfo)
