# Spec: RouteGuard Component (moderate)

Module: `frontend/src/components/RouteGuard.tsx` | Tests: `frontend/tests/unit/components/RouteGuard.test.tsx`

## FRs
- **FR-022:** Backend enforces RBAC on every API endpoint. The `RouteGuard` provides frontend-side advisory protection — hiding pages from unauthorized users and redirecting direct URL access. "URL 直接存取亦受同樣管控（後端強制檢查,前端隱藏入口）."
- **FR-021:** If auth state has not yet loaded (`isLoading: true`), show a loading indicator rather than redirecting — the user may be authenticated via SSO cookie.

## Exports
- `RouteGuard` — React component: wraps protected routes. Renders children only when the authenticated user has at least one of the required roles.

## Imports
- `react`: `ReactNode`
- `react-router-dom`: `Navigate`
- `../stores/auth-store`: `useAuthStore`
- `@mantine/core`: `Center`, `Loader`

## Props Interface
```typescript
interface RouteGuardProps {
  roles: string[];       // Required: at least one of these roles must be present
  children: ReactNode;
}
```

## Behavior Decision Tree

```
isLoading === true
  → Render <Center><Loader /></Center> (spinner, no redirect yet)

isLoading === false AND isAuthenticated === false
  → <Navigate to="/" replace />  (redirect to login page)

isLoading === false AND isAuthenticated === true AND hasAnyRole(...roles) === true
  → Render children (access granted)

isLoading === false AND isAuthenticated === true AND hasAnyRole(...roles) === false
  → <Navigate to="/403" replace />  (redirect to ForbiddenPage)
```

`hasAnyRole` is used (not `hasRole`) because routes grant access to any ONE of the listed roles.

## Side-Effects
- None. Pure rendering logic based on auth store state.
- The store's `fetchUser()` is NOT called here — that is the responsibility of the root layout or `AppRouter`.

## Gotchas
- **Do NOT call `fetchUser()` inside `RouteGuard`.** The guard is read-only. Calling `fetchUser()` here would trigger re-fetches on every route navigation.
- Empty `roles` array: treat as "any authenticated user" (return children if `isAuthenticated`). Document this behavior.
- The spinner during `isLoading` prevents a flash of the 403 page while auth state loads on page refresh.
- Test setup must use the test auth provider pattern (inject preset state via `useAuthStore.setState(...)`) — do NOT mock the auth store with `vi.mock`.

## Tests
1. **Loading state:** When `isLoading: true`, renders a spinner and does not redirect or render children.
2. **Unauthenticated:** When `isAuthenticated: false` and not loading, redirects to `/`.
3. **Authorized:** When `isAuthenticated: true` and the user has a role matching the `roles` prop, renders children.
4. **Unauthorized:** When `isAuthenticated: true` but user has no matching role, redirects to `/403`.
5. **Multiple roles:** When `roles={['FinanceAdmin', 'SystemAdmin']}` and the user has `FinanceAdmin`, access is granted.

## Consistency Constraints
FCR-002: This page component is wrapped in `<RouteGuard roles={[...exact roles from PRD section 5...]}>`. The route appears in the sidebar only for those roles.
FCR-007: Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
