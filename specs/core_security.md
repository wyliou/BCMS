# Spec: core/security (M10)

**Batch:** 2
**Complexity:** Complex

## 1. Module Paths & Test Paths

| File | Test |
|---|---|
| `backend/src/app/core/security/auth_service.py` | `backend/tests/unit/security/test_auth_service.py`, `backend/tests/integration/security/test_auth_service.py` |
| `backend/src/app/core/security/jwt.py` | `backend/tests/unit/security/test_jwt.py` |
| `backend/src/app/core/security/sessions.py` | `backend/tests/integration/security/test_sessions.py` |
| `backend/src/app/core/security/rbac.py` | `backend/tests/unit/security/test_rbac.py` |
| `backend/src/app/core/security/csrf.py` | `backend/tests/unit/security/test_csrf.py` |
| `backend/src/app/core/security/models.py` | n/a |
| `backend/src/app/api/v1/auth.py` | `backend/tests/api/test_auth.py` |
| `backend/src/app/api/v1/admin/users.py` | `backend/tests/api/test_admin_users.py` |

**Adjacent endpoint shipped in Batch 2** (user-management adjacent):
`backend/src/app/api/v1/admin/org_units.py` — includes `PATCH /admin/org-units/{id}` to set `excluded_for_cycle_ids JSONB` (FR-002 decision). Batch 4 cycles will consume the flag; the PATCH endpoint itself ships here because it is admin/user-management scope. Test: `backend/tests/api/test_admin_org_units.py`.

---

## 2. Functional Requirements

### FR-021 — Enterprise SSO Authentication

- **Input:** OIDC/SAML callback from IdP containing identity claims and group membership attributes.
- **Role mapping:** Driven by `BC_SSO_ROLE_MAPPING` environment variable (JSON map of IdP group → `Role` enum member). Mapping is evaluated at callback time, not cached.
- **Locked defaults (not overridable):**
  - NO local account fallback. If a login attempt arrives without a valid IdP callback, return `AUTH_001`.
  - If the IdP is unreachable (network timeout, DNS failure, non-2xx response from OIDC well-known endpoint), raise `AUTH_001` ("驗證服務暫時無法使用").
  - If the IdP callback succeeds but no role can be mapped from the user's group attributes, raise `AUTH_003` ("使用者尚未授權") and write an `AuditAction.AUTH_FAILED` entry.
- **On success:**
  - Upsert `User` record (keyed on `sso_id_hash` — HMAC of IdP subject). Never store raw `sso_id`.
  - Store raw email encrypted via `encrypt_field`; store `email_hash = hmac_lookup_hash(email.encode())` for deduplication lookups.
  - Mint short-lived access JWT (`exp = BC_JWT_ACCESS_MINUTES`, default 15 min) via `jwt.py`.
  - Mint refresh token: random 32-byte secret → AES-GCM encrypt → store in `sessions` table as `refresh_token_encrypted`; store `hmac_lookup_hash(raw_token)` in `refresh_token_hash` for lookup without decryption.
  - Set cookies `bc_session` (HttpOnly, Secure, SameSite=Lax, path=/), `bc_refresh` (HttpOnly, Secure, SameSite=Strict, path=/auth/refresh), `bc_csrf` (NOT HttpOnly — readable by JS, SameSite=Strict).
- **Session idle timeout:** `BC_SESSION_IDLE_MINUTES` (default 30). Enforced by checking `sessions.last_active_at` on every `current_user` resolution. Expired sessions raise `AUTH_001`.
- **Audit:** Write `AuditAction.LOGIN_SUCCESS` after commit on success; `AuditAction.AUTH_FAILED` on IdP-down or mapping failure.

### FR-022 — Role-Based Data Visibility (RBAC)

- **Roles (StrEnum `Role`):** `SystemAdmin`, `FinanceAdmin`, `HRAdmin`, `FilingUnitManager`, `UplineReviewer`, `CompanyReviewer`, `ITSecurityAuditor`.
- **Scope rules (from PRD §5):**
  - `FilingUnitManager`: org_unit_id scoped to own unit only.
  - `UplineReviewer`: org tree scoped — all `org_units` where the unit is a descendant of user's `org_unit_id` (recursive via `parent_id`).
  - `CompanyReviewer` (`0000公司`): read-only consolidated report only; no upload state list; no dashboard items.
  - `FinanceAdmin`: global scope, all org units.
  - `HRAdmin`: can import personnel budget; read own import versions; no budget upload or other org access.
  - `SystemAdmin`: global scope including user CRUD and org unit maintenance.
  - `ITSecurityAuditor`: read-only audit log; no other resource access.
- **Enforcement:** `RBAC.require_role(*roles)` and `RBAC.require_scope(resource_type, resource_id_param)` are FastAPI `Depends` factories. Route handlers declare BOTH where the URL contains a resource id. Service layer additionally calls `RBAC.scoped_org_units(user, db)` for list queries (URL bypass protection).
- **On failure:** Raise `ForbiddenError(code="RBAC_001")` for role mismatch; `ForbiddenError(code="RBAC_002")` for scope mismatch. The global handler writes `AuditAction.RBAC_DENIED` after converting to 403 JSON.

---

## 3. Exports

```python
# core/security/auth_service.py
async def handle_sso_callback(provider: str, payload: dict) -> SessionTokens:
    """Handle IdP SSO callback, upsert user, issue session cookies.

    Args:
        provider: SSO provider identifier (e.g. "oidc", "saml").
        payload: Raw callback payload from infra.sso.

    Returns:
        SessionTokens: Opaque tokens; cookies set by the route handler.

    Raises:
        UnauthenticatedError(AUTH_001): IdP unreachable or invalid callback.
        UnauthenticatedError(AUTH_003): No role mapped for user's groups.
    """

async def refresh_session(refresh_token: str) -> SessionTokens:
    """Exchange a valid refresh token for a new access token + rotated refresh token.

    Args:
        refresh_token: Raw refresh token from bc_refresh cookie.

    Returns:
        SessionTokens: New access + refresh tokens.

    Raises:
        UnauthenticatedError(AUTH_001): Token not found, expired, or revoked.
    """

async def logout(session_id: UUID) -> None:
    """Revoke session: mark sessions row as revoked, clear cookies via caller.

    Args:
        session_id: UUID from the session record.

    Raises:
        NotFoundError: Session not found.
    """

async def current_user(request: Request) -> User:
    """Resolve authenticated user from bc_session cookie.

    Args:
        request: FastAPI Request (DI provider reads cookie).

    Returns:
        User: The authenticated user with roles populated.

    Raises:
        UnauthenticatedError(AUTH_001): Missing, expired, or invalid session.
    """

# core/security/jwt.py
def mint_access_token(user_id: UUID, roles: list[Role], exp_minutes: int) -> str:
    """Mint an HS256 JWT access token.

    Args:
        user_id: Subject claim.
        roles: List of roles encoded as 'roles' claim.
        exp_minutes: Token lifetime in minutes.

    Returns:
        str: Encoded JWT string.
    """

def verify_access_token(token: str) -> dict:
    """Verify and decode an HS256 JWT.

    Args:
        token: Encoded JWT string.

    Returns:
        dict: Decoded payload.

    Raises:
        UnauthenticatedError(AUTH_001): Expired, invalid signature, or malformed.
    """

# core/security/rbac.py
def require_role(*roles: Role) -> Callable[[User], User]:
    """FastAPI Depends factory — enforce role membership.

    Args:
        *roles: One or more acceptable Role values.

    Returns:
        Callable: Dependency that returns the User or raises ForbiddenError(RBAC_001).
    """

def require_scope(resource_type: str, resource_id_param: str) -> Callable[..., None]:
    """FastAPI Depends factory — enforce org-unit scope on a path parameter.

    Args:
        resource_type: Resource type string for audit (e.g. "org_unit").
        resource_id_param: Name of the path parameter containing the resource id.

    Returns:
        Callable: Dependency that raises ForbiddenError(RBAC_002) if out of scope.
    """

async def scoped_org_units(user: User, db: AsyncSession) -> set[UUID]:
    """Return the set of org_unit UUIDs visible to this user.

    Args:
        user: Authenticated user.
        db: Async database session.

    Returns:
        set[UUID]: Visible org unit ids. FinanceAdmin/SystemAdmin return all ids.
    """

# core/security/csrf.py
def generate_csrf_token() -> str:
    """Generate a cryptographically random CSRF token (32 bytes, hex-encoded).

    Returns:
        str: Hex-encoded token for bc_csrf cookie and X-CSRF-Token header.
    """

def verify_csrf_token(cookie_value: str, header_value: str) -> None:
    """Verify double-submit CSRF tokens match using hmac.compare_digest.

    Args:
        cookie_value: Value from bc_csrf cookie.
        header_value: Value from X-CSRF-Token request header.

    Raises:
        ForbiddenError(RBAC_001): Tokens do not match.
    """

# Exported types
class Role(StrEnum): ...           # SystemAdmin, FinanceAdmin, HRAdmin, FilingUnitManager, UplineReviewer, CompanyReviewer, ITSecurityAuditor
class SessionTokens(BaseModel): ...  # access_token, refresh_token, csrf_token, expires_at
```

---

## 4. Imports

| Module | Symbols | Notes |
|---|---|---|
| `infra.sso` | `SSOClient.exchange_code`, `SSOClient.fetch_userinfo` | Called in `handle_sso_callback`; must be called before any DB write |
| `infra.db` | `get_session`, `AsyncSession` | Session factory |
| `infra.crypto` | `encrypt_field`, `decrypt_field`, `hmac_lookup_hash` | Encrypt email + SSO id; hash refresh token for lookup |
| `core.clock` | `now_utc` | Session expiry and `last_active_at` updates |
| `domain.audit` | `AuditService.record`, `AuditAction` | Write audit entries after commit |
| `core.errors` | `UnauthenticatedError`, `ForbiddenError`, `NotFoundError`, `InfraError` | Error raising |
| `app.config` | `Settings` | `BC_SSO_ROLE_MAPPING`, `BC_JWT_SECRET`, `BC_JWT_ACCESS_MINUTES`, `BC_SESSION_IDLE_MINUTES` |

### Required Call Order in `handle_sso_callback`

1. `SSOClient.exchange_code(provider, code)` — exchange authorization code for IdP tokens. Raises `AUTH_001` on IdP failure (wrap `InfraError`).
2. `SSOClient.fetch_userinfo(id_token)` — retrieve claims and group attributes. Raises `AUTH_001` on failure.
3. Map groups → `Role` via `BC_SSO_ROLE_MAPPING`. Raise `AUTH_003` immediately if no match (no DB writes yet).
4. Open DB session; upsert `User` (keyed on `hmac_lookup_hash(sso_id)`).
5. Create `Session` row with `refresh_token_hash` and `refresh_token_encrypted`.
6. `await db.commit()`.
7. `mint_access_token(...)` and compose `SessionTokens`.
8. `await audit.record(AuditAction.LOGIN_SUCCESS, ...)` — AFTER commit (CR-006).
9. Return `SessionTokens`.

**Rationale:** Step 3 (role check) must precede any DB write so a mapping failure never creates a partial user row. Step 8 must follow step 6 per CR-006.

---

## 5. Side Effects

- Writes/upserts `users` table row on every successful login.
- Writes `sessions` table row on every successful login and refresh.
- Sets `sessions.revoked_at` on logout.
- Updates `sessions.last_active_at` on every `current_user` resolution (touch on activity).
- Writes `audit_logs` rows: `LOGIN_SUCCESS`, `LOGOUT`, `AUTH_FAILED`, `RBAC_DENIED`.
- Sets three HTTP cookies: `bc_session`, `bc_refresh`, `bc_csrf`.

---

## 6. Gotchas

- **No local accounts.** Any code path that creates a `User` without going through the SSO callback is forbidden. There is no `/auth/login` username+password endpoint.
- **Cookie names are fixed:** `bc_session` (HttpOnly), `bc_refresh` (HttpOnly, path=/auth/refresh), `bc_csrf` (NOT HttpOnly). Cookie names must not vary by environment.
- **Refresh token storage:** Only the HMAC hash is used for lookups (`WHERE refresh_token_hash = $1`). The AES-GCM ciphertext is stored for potential future key rotation. Never query by raw token string.
- **Session idle vs. absolute expiry:** The JWT encodes absolute `exp`. The session row enforces idle timeout via `last_active_at`. Both checks must pass in `current_user`.
- **RBAC scope for UplineReviewer** is computed via recursive CTE over `org_units.parent_id`. Cache the result per-request in `scoped_org_units`; do NOT cache across requests or users.
- **`PATCH /admin/org-units/{id}`** sets `excluded_for_cycle_ids JSONB[]`. This column ships in the baseline Alembic migration. The field is consumed by `CycleService.list_filing_units` in Batch 4; document the contract here but note the consumer ships later.
- **`AUTH_003` must record an audit entry** even though no user row exists (user_id may be null in audit record).
- **CSRF double-submit:** All state-mutating routes (`POST`, `PATCH`, `DELETE`) must call `verify_csrf_token` before processing. `GET` routes are exempt.

---

## 7. Verbatim Outputs (from PRD §4.8)

- IdP unreachable error message: `"驗證服務暫時無法使用"` (AUTH_001)
- Role mapping failure message: `"使用者尚未授權"` (AUTH_003)
- RBAC scope violation: 403 JSON envelope with `code: "RBAC_002"` (no verbatim user message in PRD; message template lives in ERROR_REGISTRY)

---

## 8. Consistency Constraints

**CR-001 — Error code registry single source**
*"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
Applies to: `AUTH_001`, `AUTH_003`, `RBAC_001`, `RBAC_002`.

**CR-002 — Audit action enum single source**
*"All `audit.record(...)` calls in this module use a member of `app.domain.audit.actions.AuditAction`; no string literals."*
Applies to: `LOGIN_SUCCESS`, `LOGOUT`, `AUTH_FAILED`, `RBAC_DENIED`.

**CR-006 — Audit AFTER commit, BEFORE return**
*"This service commits the DB transaction first, then calls `audit.record(...)`, then returns. If audit fails, the entire operation is rolled back (audit failure = cannot honor FR-023)."*
Applies to: `handle_sso_callback` (commit session → audit LOGIN_SUCCESS), `logout` (commit revocation → audit LOGOUT).

**CR-032 — RBAC scope matrix completeness**
*"This route declares `Depends(RBAC.require_role(...))` AND, where the URL contains a resource id, `Depends(RBAC.require_scope(resource_type, resource_id_param))`. Both must be present — `require_role` alone is insufficient for scoped resources."*
Applies to: every route in `api/v1/auth.py` and `api/v1/admin/users.py` and `api/v1/admin/org_units.py`.

---

## 9. Tests

### `test_auth_service.py` (unit — uses `infra.sso.fake_sso`)

1. **`test_handle_sso_callback_success`** — happy path: fake_sso returns valid claims, role mapping resolves `FinanceAdmin`, user upserted, `SessionTokens` returned with all three token fields non-empty, `LOGIN_SUCCESS` audit record created after DB commit.
2. **`test_handle_sso_callback_idp_unreachable`** — fake_sso raises `InfraError`; assert `UnauthenticatedError` with code `AUTH_001` is raised; no user row created; `AUTH_FAILED` audit entry written.
3. **`test_handle_sso_callback_no_role_mapping`** — IdP returns valid claims but no matching group in `BC_SSO_ROLE_MAPPING`; assert `UnauthenticatedError` with code `AUTH_003`; no user row; `AUTH_FAILED` audit entry with `user_id=None`.
4. **`test_refresh_session_success`** — insert session row with known hash; call `refresh_session`; assert new `SessionTokens` returned, old refresh token hash invalidated, new row created, `last_active_at` updated.
5. **`test_refresh_session_expired`** — insert session row with `expires_at` in the past; assert `UnauthenticatedError(AUTH_001)`.

### `test_jwt.py` (unit)

1. **`test_mint_and_verify_round_trip`** — mint token with known `user_id` and roles; verify decodes same values.
2. **`test_verify_expired_token`** — patch `now_utc` to past; mint token; advance clock past `exp`; assert `UnauthenticatedError(AUTH_001)`.
3. **`test_verify_tampered_signature`** — alter one character of the encoded token; assert `UnauthenticatedError(AUTH_001)`.

### `test_rbac.py` (unit)

1. **`test_require_role_matching_role`** — call dependency with `User(role=FinanceAdmin)`; assert user returned unchanged.
2. **`test_require_role_wrong_role`** — call dependency with `User(role=HRAdmin)` for route requiring `FinanceAdmin`; assert `ForbiddenError(RBAC_001)`.
3. **`test_scoped_org_units_finance_admin`** — `FinanceAdmin` receives all org unit ids.
4. **`test_scoped_org_units_filing_unit_manager`** — `FilingUnitManager` with `org_unit_id=X` receives only `{X}`.
5. **`test_scoped_org_units_upline_reviewer`** — reviewer at 1000-level node; verify recursive traversal returns all descendant unit ids.

### `test_csrf.py` (unit)

1. **`test_generate_csrf_token_length`** — 64-char hex string.
2. **`test_verify_csrf_matching_tokens`** — matching pair passes silently.
3. **`test_verify_csrf_mismatched_tokens`** — different pair raises `ForbiddenError`.

### `test_auth.py` (API)

1. **`test_sso_callback_sets_cookies`** — POST to `/api/v1/auth/callback`; assert response contains `Set-Cookie` headers for `bc_session`, `bc_refresh`, `bc_csrf`.
2. **`test_sso_callback_idp_down_returns_401`** — fake_sso configured to error; assert 401 JSON envelope with `error.code == "AUTH_001"`.
3. **`test_auth_me_requires_valid_session`** — GET `/api/v1/auth/me` without cookie; assert 401.
4. **`test_auth_me_returns_user`** — GET with valid session cookie; assert 200 with `user_id` and `roles`.
5. **`test_logout_revokes_session`** — POST `/api/v1/auth/logout`; subsequent GET `/auth/me` with same cookie returns 401.

### `test_admin_users.py` (API)

1. **`test_list_users_requires_system_admin`** — GET as `FinanceAdmin`; assert 403.
2. **`test_list_users_as_system_admin`** — GET as `SystemAdmin`; assert 200 with user list.
3. **`test_patch_user_role`** — PATCH `/api/v1/admin/users/{id}` with new role; assert updated `roles` in response.
4. **`test_patch_org_unit_excluded_cycles`** — PATCH `/api/v1/admin/org-units/{id}` with `excluded_for_cycle_ids`; assert 200 and field persisted.
