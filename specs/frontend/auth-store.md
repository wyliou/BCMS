# Spec: Zustand Auth Store (moderate)

Module: `frontend/src/stores/auth-store.ts` | Tests: `frontend/tests/unit/stores/auth-store.test.ts`

## FRs
- **FR-021:** Auth state is derived from `GET /auth/me`. No tokens stored. The store exposes `isAuthenticated`, `isLoading`, and user profile.
- **FR-022:** `hasRole` / `hasAnyRole` helpers enable role-based visibility across all pages. RBAC decisions in the frontend are advisory (UI hiding); the backend enforces all role checks authoritatively.

## Exports
- `useAuthStore` — Zustand hook: provides `AuthState` slice to any component. The only export from this file.

## Imports
- `zustand`: `create`
- `../api/auth`: `fetchMe`, `logout`, `WhoAmIResponse`

## Interface
```typescript
interface AuthState {
  user: WhoAmIResponse | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  fetchUser: () => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (...roles: string[]) => boolean;
  hasAnyRole: (...roles: string[]) => boolean;
}
```

## Store Implementation Requirements

### `fetchUser()`
1. Sets `isLoading: true`.
2. Calls `fetchMe()` from `api/auth.ts`.
3. On success: sets `user`, `isAuthenticated: true`, `isLoading: false`.
4. On error (any HTTP error): sets `user: null`, `isAuthenticated: false`, `isLoading: false`. Does not rethrow — callers check `isAuthenticated` after calling.
5. Special case: 401 response is handled by the axios interceptor transparently (refresh → retry). If interceptor redirects, `fetchUser` never resolves — this is expected behavior.

### `logout()`
1. Calls `logout()` from `api/auth.ts` (which calls `POST /auth/logout`).
2. Regardless of whether the server call succeeds, sets `user: null`, `isAuthenticated: false`.
3. Navigates to `/` — since Zustand store lives outside React, navigation must use `window.location.href = '/'` rather than `useNavigate()`.

### `hasRole(...roles: string[])`
Returns `true` if ALL of the specified roles are present in `user.roles`. Returns `false` if `user` is null.

### `hasAnyRole(...roles: string[])`
Returns `true` if AT LEAST ONE of the specified roles is present in `user.roles`. Returns `false` if `user` is null.

### Initial State
```typescript
{
  user: null,
  isAuthenticated: false,
  isLoading: false,
}
```
`isLoading` starts as `false` (not `true`) — the app does not initiate a user fetch until `fetchUser()` is called. `AppRouter` or the shell layout calls `fetchUser()` on mount.

## Side-Effects
- `fetchUser()` calls `GET /auth/me` (via `api/auth.ts`).
- `logout()` calls `POST /auth/logout` (via `api/auth.ts`) and navigates to `/`.

## Gotchas
- **No localStorage/sessionStorage.** Auth state is ephemeral. Page refresh triggers a new `fetchUser()` call.
- **No direct `bc_session` / `bc_refresh` cookie reads.** The store is a consumer of `/auth/me` output only.
- `hasRole` is not the same as `hasAnyRole`. Guard components use `hasAnyRole` unless the route requires ALL specified roles.
- Zustand store is a module-level singleton; tests must use `useAuthStore.setState(...)` to set up pre-conditions rather than mocking the store directly. Test files must reset state with `useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false })` in `beforeEach`.
- The store does NOT subscribe to auth changes from other tabs or windows (no BroadcastChannel). Session expiry is handled by the axios interceptor redirecting to SSO login.

## Tests
1. **fetchUser success:** After `fetchUser()` resolves, `isAuthenticated` is `true`, `user` is set to the mock `WhoAmIResponse`, and `isLoading` is `false`.
2. **fetchUser failure:** When `fetchMe()` rejects (500 error), `isAuthenticated` is `false`, `user` is `null`, `isLoading` is `false`.
3. **logout:** After `logout()` resolves, `user` is `null` and `isAuthenticated` is `false` regardless of server response.
4. **hasRole:** Returns `true` when the user has the specified role; `false` when not; `false` when `user` is null.
5. **hasAnyRole:** Returns `true` when the user has at least one of the specified roles; `false` when none match.

## Consistency Constraints
FCR-002: This page component is wrapped in `<RouteGuard roles={[...exact roles from PRD section 5...]}>`. The route appears in the sidebar only for those roles.
FCR-011: This module does not read `bc_session` or `bc_refresh` cookies. It does not write to `localStorage` or `sessionStorage` for auth purposes.
