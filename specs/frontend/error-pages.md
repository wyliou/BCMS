# Spec: 403/404 Error Pages (simple)

## 403 Forbidden Page

Module: `frontend/src/pages/errors/ForbiddenPage.tsx` | Tests: `frontend/tests/unit/pages/errors/ForbiddenPage.test.tsx`

### Exports
- `ForbiddenPage` — React component: displays a 403 Forbidden message. Shown when `RouteGuard` redirects due to insufficient roles, or when the API returns a 403 that is not intercepted.

### Imports
- `react-i18next`: `useTranslation`
- `react-router-dom`: `useNavigate`
- `@mantine/core`: `Center`, `Title`, `Text`, `Button`

### FRs
- **FR-022:** Backend enforces RBAC on every API endpoint. The frontend hides entry points (nav items) per role, but the 403 page is the fallback for direct URL access. No retry — 403 is terminal per architecture Session & Token Transport.

### Behavior
- Displays `errors.forbidden_title` heading and `errors.forbidden_message` body (i18n keys).
- "回首頁" button navigates to `/` (LoginPage, which redirects to dashboard if authenticated).
- No automatic redirect or retry.

### Tests
1. Renders 403 heading using i18n key `errors.forbidden_title`.
2. Renders the back-to-home button.
3. Clicking the back-to-home button navigates to `/`.
4. No retry button or spinner is present (403 is terminal).

### Constraints
FCR-004: All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.

---

## 404 Not Found Page

Module: `frontend/src/pages/errors/NotFoundPage.tsx` | Tests: `frontend/tests/unit/pages/errors/NotFoundPage.test.tsx`

### Exports
- `NotFoundPage` — React component: displays a 404 Not Found message. Rendered by the React Router catch-all route `path="*"`.

### Imports
- `react-i18next`: `useTranslation`
- `react-router-dom`: `useNavigate`
- `@mantine/core`: `Center`, `Title`, `Text`, `Button`

### Behavior
- Displays `errors.not_found_title` heading and `errors.not_found_message` body.
- "回首頁" button navigates to `/`.
- No automatic redirect.

### Tests
1. Renders 404 heading using i18n key `errors.not_found_title`.
2. Renders the back-to-home button.
3. Clicking the back-to-home button navigates to `/`.
4. Accessible: heading element has correct role/tag (`<h1>` or equivalent).

### Constraints
FCR-004: All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
