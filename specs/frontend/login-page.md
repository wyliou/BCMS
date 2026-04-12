# Spec: SSO Login Landing Page (simple)

Module: `frontend/src/pages/auth/LoginPage.tsx` | Tests: `frontend/tests/unit/pages/auth/LoginPage.test.tsx`

## Exports
- `LoginPage` — React component: SSO login landing. Displays a centered card with the platform name and an "SSO 登入" button that redirects to `/api/v1/auth/sso/login?return_to=/dashboard`.

## Imports
- `react-i18next`: `useTranslation`
- `@mantine/core`: `Button`, `Center`, `Card`, `Title`, `Text`
- `../stores/auth-store`: `useAuthStore` — redirect to `/dashboard` if already authenticated

## FRs
- **FR-021:** Federated SSO entry point. No local credentials. Button navigates to `GET /auth/sso/login?return_to={path}` which triggers a 302 redirect to the IdP. Error states: IdP unavailable → `AUTH_001` (display i18n key `auth.sso_unavailable`); no role mapping → `AUTH_003` (display i18n key `auth.unauthorized`).

## Side-Effects
- On mount: reads auth store; if already authenticated, redirects to `/dashboard` via `useNavigate`.
- Button click: `window.location.href = '/api/v1/auth/sso/login?return_to=/dashboard'` (full-page navigation, not axios call — SSO redirect must be a real browser navigation).

## Gotchas
- Do NOT use `axios` or `apiClient` for the SSO redirect. This is a browser navigation, not an AJAX call.
- `return_to` query param must be URL-encoded.
- If the URL carries `?error=AUTH_003` (set by backend after failed SSO callback), display the appropriate i18n error message.
- No form; no credentials input. This page is intentionally minimal per PRD §8.2 (FilingUnitManager: minimal UI).

## Tests
1. Renders the platform title and SSO login button.
2. Clicking the login button navigates to `/api/v1/auth/sso/login?return_to=/dashboard`.
3. When auth store reports `isAuthenticated: true`, redirects to `/dashboard` without showing the login UI.
4. When URL contains `?error=AUTH_003`, renders the i18n error message `auth.unauthorized`.

## Constraints
FCR-004: All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
FCR-011: This module does not read `bc_session` or `bc_refresh` cookies. It does not write to `localStorage` or `sessionStorage` for auth purposes.
