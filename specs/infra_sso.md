# Spec: infra/sso

Module: `backend/src/app/infra/sso/__init__.py` (+ `_oidc.py`, `_saml.py`, `fake_sso.py` if needed for ≤500 lines)
Tests: `backend/tests/unit/infra/test_sso.py`

## FRs

- FR-021 (OIDC/SAML callback → role mapping; AUTH_001–003)

## Exports

```python
from dataclasses import dataclass

@dataclass
class SSOUserInfo:
    """Normalized user profile returned by the SSO provider.

    Attributes:
        sso_id (str): Unique subject identifier from the IdP (sub claim / SAML NameID).
        email (str): User email.
        display_name (str): Display name.
        raw_groups (list[str]): Raw IdP group memberships used for role mapping.
    """
    sso_id: str
    email: str
    display_name: str
    raw_groups: list[str]


@dataclass
class CallbackResult:
    """Result of processing the SSO callback.

    Attributes:
        user_info (SSOUserInfo): Normalized profile.
        mapped_roles (list[str]): System roles mapped from raw_groups via BC_SSO_ROLE_MAPPING.
        id_token (str | None): OIDC id_token string (None for SAML).
    """
    user_info: SSOUserInfo
    mapped_roles: list[str]
    id_token: str | None


class SSOClient:
    """Authlib-based OIDC/SAML client.

    Protocol (oidc or saml2) is determined by settings.sso_protocol.
    Constructed once at startup; shared across requests.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize OIDC or SAML2 client from settings.

        Args:
            settings (Settings): Application settings.
        """

    def get_authorization_url(self, state: str, nonce: str) -> str:
        """Return the IdP authorization URL for the login redirect.

        Args:
            state (str): CSRF state token (stored in session cookie).
            nonce (str): OIDC nonce (stored in session cookie for verification).

        Returns:
            str: Full authorization URL to redirect the browser to.

        Raises:
            InfraError: code='AUTH_001' if IdP discovery fails.
        """

    async def exchange_code(self, code: str, state: str) -> dict[str, object]:
        """Exchange the authorization code for tokens at the IdP token endpoint.

        Args:
            code (str): Authorization code from callback query parameter.
            state (str): State echoed back by IdP; must match session-stored value.

        Returns:
            dict[str, object]: Raw token response (access_token, id_token, etc.).

        Raises:
            InfraError: code='AUTH_001' if IdP is unreachable.
            InfraError: code='AUTH_002' if state/signature mismatch.
        """

    async def fetch_userinfo(self, access_token: str) -> SSOUserInfo:
        """Fetch and normalize the user profile from the IdP userinfo endpoint.

        For OIDC: calls the /userinfo endpoint. For SAML2: extracts from assertion attributes.
        Normalizes to SSOUserInfo regardless of protocol.

        Args:
            access_token (str): Access token from exchange_code (OIDC) or SAML assertion token.

        Returns:
            SSOUserInfo: Normalized user profile.

        Raises:
            InfraError: code='AUTH_001' if IdP userinfo endpoint is unreachable.
        """

    def map_roles(self, raw_groups: list[str]) -> list[str]:
        """Map IdP group names to system role names using BC_SSO_ROLE_MAPPING.

        Args:
            raw_groups (list[str]): Raw group memberships from IdP.

        Returns:
            list[str]: System role names (subset of Role StrEnum values).
                Empty list if no groups match.

        Raises:
            InfraError: code='AUTH_003' if no groups map to any system role.
                Note: AUTH_003 is a domain concern — this method returns an empty
                list and the caller (core/security) raises AUTH_003.
        """

    async def process_callback(self, code: str, state: str) -> CallbackResult:
        """Full callback pipeline: exchange code, fetch userinfo, map roles.

        Convenience method combining exchange_code + fetch_userinfo + map_roles.

        Args:
            code (str): Authorization code.
            state (str): State token.

        Returns:
            CallbackResult: Normalized result including mapped roles.
        """


class FakeSSO:
    """In-memory test double for SSOClient.

    Configurable to return fixed user info or raise auth errors for testing.
    """

    def __init__(
        self,
        *,
        sso_id: str = "test-sso-id",
        email: str = "test@example.com",
        display_name: str = "Test User",
        raw_groups: list[str] | None = None,
        mapped_roles: list[str] | None = None,
        should_fail_auth_001: bool = False,
        should_fail_auth_002: bool = False,
    ) -> None:
        """Configure FakeSSO behavior.

        Args:
            sso_id (str): SSO subject to return.
            email (str): Email to return.
            display_name (str): Display name to return.
            raw_groups (list[str] | None): Raw groups. Defaults to [].
            mapped_roles (list[str] | None): Mapped roles. Defaults to ['FinanceAdmin'].
            should_fail_auth_001 (bool): If True, raise InfraError('AUTH_001', ...) on exchange.
            should_fail_auth_002 (bool): If True, raise InfraError('AUTH_002', ...) on exchange.
        """

    def get_authorization_url(self, state: str, nonce: str) -> str:
        """Return fake authorization URL.

        Args:
            state (str): State token.
            nonce (str): Nonce.

        Returns:
            str: Fake URL string.
        """

    async def exchange_code(self, code: str, state: str) -> dict[str, object]:
        """Return fake token response or raise configured error.

        Args:
            code (str): Authorization code.
            state (str): State token.

        Returns:
            dict[str, object]: Fake token dict.

        Raises:
            InfraError: code='AUTH_001' if should_fail_auth_001.
            InfraError: code='AUTH_002' if should_fail_auth_002.
        """

    async def fetch_userinfo(self, access_token: str) -> SSOUserInfo:
        """Return configured SSOUserInfo.

        Args:
            access_token (str): Ignored in fake.

        Returns:
            SSOUserInfo: Configured user info.
        """

    def map_roles(self, raw_groups: list[str]) -> list[str]:
        """Return configured mapped_roles.

        Args:
            raw_groups (list[str]): Ignored in fake.

        Returns:
            list[str]: Configured mapped roles.
        """

    async def process_callback(self, code: str, state: str) -> CallbackResult:
        """Return fake CallbackResult.

        Args:
            code (str): Ignored in fake.
            state (str): Ignored in fake.

        Returns:
            CallbackResult: Configured result.
        """
```

## Imports

| Module | Symbols |
|---|---|
| `authlib.integrations.httpx_client` | `AsyncOAuth2Client` (OIDC) |
| `authlib.oauth2.rfc6749` | relevant token types |
| `httpx` | `AsyncClient`, `HTTPStatusError`, `TimeoutException` |
| `app.config` | `Settings` |
| `app.core.errors` | `InfraError` |
| `structlog` | `get_logger` |

## Side Effects

- `SSOClient.__init__` may perform OIDC discovery (fetch `.well-known/openid-configuration`) on first authorization URL request. Discovery result is cached in-instance.
- `exchange_code` and `fetch_userinfo` make outbound HTTP calls to the IdP.

## Role Mapping Convention

`map_roles(raw_groups)` iterates `settings.sso_role_mapping` (a `dict[str, str]` from `BC_SSO_ROLE_MAPPING`). For each IdP group in `raw_groups`, if the group name is a key in the mapping, the corresponding value is added to the result. Unmapped groups are silently ignored. The caller (`core/security.auth_service`) raises `AUTH_003` if the returned list is empty.

## Identifier Mapping Note (CR for identifier mapping)

The `sso_id` from the IdP is stored in `users.sso_id_enc` (AES-GCM encrypted) and `users.sso_id_hash` (HMAC-SHA256 via `hmac_lookup_hash`). The user lookup at login time queries by `sso_id_hash`. This module does NOT handle the hashing or encryption — it returns plaintext `sso_id`; `core/security` owns the hash/encrypt lifecycle.

## Gotchas

- SAML2 support is protocol-branched in `__init__`: if `settings.sso_protocol == "saml2"`, the SAML implementation path is used instead of OIDC. The `exchange_code` and `fetch_userinfo` signatures are identical for both protocols from the caller's perspective.
- `AUTH_001` is raised when an `httpx.TimeoutException` or connection-level error occurs. HTTP 4xx responses from IdP are typically `AUTH_002`.
- `state` validation (must match the value stored in the session cookie) is performed by `core/security`, not here. `SSOClient.exchange_code` passes the `state` to Authlib's token exchange, which validates it against the `state` parameter if using the Authlib session pattern.

## Consistency Constraints

- **CR-001 Stage B check:** *"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
  - Raises `InfraError("AUTH_001", ...)` and `InfraError("AUTH_002", ...)`.

## Tests

1. `test_fake_sso_returns_configured_user_info` — `FakeSSO().process_callback(...)` returns `CallbackResult` with configured fields.
2. `test_fake_sso_auth_001_failure` — `should_fail_auth_001=True`; `exchange_code` raises `InfraError("AUTH_001", ...)`.
3. `test_fake_sso_auth_002_failure` — `should_fail_auth_002=True`; `exchange_code` raises `InfraError("AUTH_002", ...)`.
4. `test_map_roles_filters_unmapped_groups` — `raw_groups=["BC_UNKNOWN"]`; returns `[]`.
5. `test_map_roles_maps_known_groups` — `raw_groups=["BC_FINANCE"]` with mapping `{"BC_FINANCE": "FinanceAdmin"}`; returns `["FinanceAdmin"]`.
6. `test_map_roles_multiple_roles` — two matching groups; both roles returned.
