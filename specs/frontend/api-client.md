# Spec: Axios API Client with CSRF Interceptor (moderate)

Module: `frontend/src/api/client.ts` | Tests: `frontend/tests/unit/api/client.test.ts`

## FRs
- **FR-021 (Session & Token Transport):** Cookie-based SSO. Browser never sees JWT. `withCredentials: true` ensures session cookies (`bc_session`, `bc_refresh`) are sent with every request. On 401 → silent token refresh via `POST /auth/refresh` → retry original request. On refresh failure → redirect to SSO login.
- **FCR-001:** Every POST/PATCH/DELETE request carries `X-CSRF-Token` header derived from the `bc_csrf` JS-readable cookie. Backend verifies the double-submit cookie match.

## Exports
- `apiClient` — `AxiosInstance`: singleton configured axios instance. The only axios instance in the codebase. All API modules import and use this.

## Imports
- `axios`: `axios`, `AxiosInstance`, `AxiosRequestConfig`, `AxiosError`, `InternalAxiosRequestConfig`

## Implementation Requirements

### Instance Configuration
```typescript
const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  withCredentials: true,  // send cookies on every request
  headers: {
    'Content-Type': 'application/json',
  },
});
```

### Request Interceptor (CSRF)
Reads the `bc_csrf` cookie and injects it as `X-CSRF-Token` on every state-changing method:
```typescript
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const method = config.method?.toUpperCase();
  if (method === 'POST' || method === 'PATCH' || method === 'DELETE') {
    const csrfToken = getCsrfToken(); // reads document.cookie
    if (csrfToken) {
      config.headers['X-CSRF-Token'] = csrfToken;
    }
  }
  return config;
});
```

`getCsrfToken()` is a private helper:
```typescript
function getCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)bc_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}
```

### Response Interceptor (401 Refresh)
```typescript
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        await axios.post('/api/v1/auth/refresh', null, { withCredentials: true });
        return apiClient(originalRequest);
      } catch {
        window.location.href = '/api/v1/auth/sso/login?return_to=' + encodeURIComponent(window.location.pathname);
      }
    }
    return Promise.reject(error);
  }
);
```

Key behaviors:
- `_retry` flag prevents infinite refresh loops.
- The refresh call uses a bare `axios.post` (not `apiClient`) to avoid triggering the interceptor again.
- On refresh failure, redirect is a full-page navigation to SSO login, NOT `useNavigate()`.
- 403 responses are NOT intercepted; they propagate to the caller for handling.

## Side-Effects
- **Module-load:** Creates the singleton `apiClient` instance. Registers request and response interceptors.
- **Per-request (POST/PATCH/DELETE):** Reads `document.cookie` to extract `bc_csrf`.
- **On 401:** Calls `POST /auth/refresh` and may redirect to SSO login.

## Gotchas
- The refresh call must NOT go through `apiClient` itself (would trigger the 401 interceptor recursively). Use a separate one-off `axios.post`.
- `window.location.href` assignment is acceptable here because SSO redirect requires a full browser navigation. This is the one exception to the no-`window.open` rule.
- `import.meta.env.VITE_API_BASE_URL` must be used (not `process.env`). Fallback to `/api/v1` for tests where the env var is not set.
- Never read `bc_session` or `bc_refresh` cookies; they are HttpOnly and will not be visible to `document.cookie`.
- The `Content-Type: multipart/form-data` header must be omitted (let axios set the boundary) when sending `FormData`. API modules must use `undefined` for the content-type in multipart calls and let axios detect it.

## Tests
1. **CSRF header injection:** Making a `POST` request through `apiClient` in a jsdom environment where `bc_csrf=test-token` is in `document.cookie` results in the request having `X-CSRF-Token: test-token` header.
2. **CSRF not on GET:** Making a `GET` request does NOT set the `X-CSRF-Token` header.
3. **401 → refresh → retry:** When an MSW handler returns 401 for the first call and 200 for the second call (after the refresh intercept calls `POST /auth/refresh`), the response interceptor retries the original request and resolves.
4. **Refresh failure → redirect:** When the refresh call itself returns 401, `window.location.href` is set to the SSO login URL.
5. **baseURL from env:** `apiClient.defaults.baseURL` equals `import.meta.env.VITE_API_BASE_URL` when set.

## Consistency Constraints
FCR-001: This module uses the shared `apiClient` from `src/api/client.ts` for all HTTP requests. It does NOT create its own axios instance or use raw `fetch()`. The CSRF token is read from `document.cookie` and set as `X-CSRF-Token` by the request interceptor.
FCR-009: The API function in this module defines a zod schema for the response and calls `.parse()` or `.safeParse()` on `response.data` before returning.
FCR-011: This module does not read `bc_session` or `bc_refresh` cookies. It does not write to `localStorage` or `sessionStorage` for auth purposes.
FCR-013: Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
