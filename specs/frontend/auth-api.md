# Spec: Auth API Module (simple)

Module: `frontend/src/api/auth.ts` | Tests: `frontend/tests/unit/api/auth.test.ts`

## Exports
- `fetchMe()` — `(): Promise<WhoAmIResponse>` — calls `GET /auth/me`; returns validated user profile.
- `logout()` — `(): Promise<void>` — calls `POST /auth/logout`; server clears cookies.
- `refresh()` — `(): Promise<void>` — calls `POST /auth/refresh`; transparent token refresh.

## Imports
- `./client`: `apiClient` (AxiosInstance)
- `zod`: `z`

## Zod Schemas
```typescript
const WhoAmISchema = z.object({
  user_id: z.string().uuid(),
  role: z.string().nullable(),
  roles: z.array(z.string()),
  org_unit_id: z.string().uuid().nullable(),
  display_name: z.string(),
});
export type WhoAmIResponse = z.infer<typeof WhoAmISchema>;
```

## Function Contracts
- `fetchMe()`: `GET /auth/me` → parse with `WhoAmISchema.parse(response.data)` → return typed object. On 401, the axios interceptor in `client.ts` handles refresh transparently.
- `logout()`: `POST /auth/logout` → expect 204 → return void. Never read response body.
- `refresh()`: `POST /auth/refresh` → expect 204 → return void. Called by client interceptor only; components must not call this directly.

## Side-Effects
None beyond HTTP calls. Cookie management is handled by the browser/server.

## Gotchas
- `refresh()` is reserved for the axios interceptor in `client.ts`. Page components call `useAuthStore().logout()` (which calls this), not `refresh()` directly.
- `WhoAmIResponse.roles` is an array; a user may have multiple roles in future, but current RBAC uses the first role. `hasRole` / `hasAnyRole` in the auth store handle this.
- `role: null` means the SSO subject has no mapped role (AUTH_003 scenario); auth store should treat this as unauthenticated.

## Tests
1. `fetchMe()` calls `GET /auth/me` and returns a `WhoAmIResponse` on a valid mock response.
2. `fetchMe()` throws a zod error when the response shape is invalid (missing `user_id`).
3. `logout()` calls `POST /auth/logout` with `withCredentials` (via shared client) and returns void.
4. `refresh()` calls `POST /auth/refresh` and returns void on 204.
5. `fetchMe()` propagates an axios error when the server responds with 503 (SSO unavailable).

## Constraints
FCR-001: This module uses the shared `apiClient` from `src/api/client.ts` for all HTTP requests. It does NOT create its own axios instance or use raw `fetch()`. The CSRF token is read from `document.cookie` and set as `X-CSRF-Token` by the request interceptor.
FCR-009: The API function in this module defines a zod schema for the response and calls `.parse()` or `.safeParse()` on `response.data` before returning.
FCR-011: This module does not read `bc_session` or `bc_refresh` cookies. It does not write to `localStorage` or `sessionStorage` for auth purposes.
FCR-013: Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
