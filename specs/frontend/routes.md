# Spec: React Router Config (moderate)

Module: `frontend/src/routes/index.tsx` | Tests: `frontend/tests/unit/routes/routes.test.tsx`

## FRs
- **FR-022:** Every protected route is wrapped in `<RouteGuard roles={[...]}>`. Role lists match the PRD §5 role permission table and must align with the backend `require_role(...)` checks on consumed API endpoints.
- **FR-021:** Unauthenticated users are redirected to the SSO login page (`/`), not the native login form.

## Exports
- `AppRouter` — default export React component: declares all application routes using React Router `<Routes>` and `<Route>`.

## Imports
- `react-router-dom`: `Routes`, `Route`
- `react`: `lazy`, `Suspense`
- `../components/RouteGuard`: `RouteGuard`
- `../components/ShellLayout`: `ShellLayout`
- `../components/ErrorBoundary`: `ErrorBoundary`
- All page components (lazy-loaded)

## Route Structure

All authenticated routes are rendered inside `<ShellLayout>` which provides the sidebar and header. The `ShellLayout` renders `<Outlet />` for page content.

```
/                  → <LoginPage />           (public, no guard)
/403               → <ForbiddenPage />       (public, no guard)
/*                 → <NotFoundPage />        (public, no guard — catch-all)

(Protected routes — inside ShellLayout as parent route)
/upload            → RouteGuard(['FilingUnitManager'])
                     → <UploadPage /> (lazy)

/dashboard         → RouteGuard(['FinanceAdmin', 'UplineReviewer', 'CompanyReviewer', 'SystemAdmin'])
                     → <DashboardPage /> (lazy)

/reports           → RouteGuard(['FinanceAdmin', 'UplineReviewer', 'CompanyReviewer', 'SystemAdmin'])
                     → <ConsolidatedReportPage /> (lazy)

/personnel-import  → RouteGuard(['HRAdmin', 'SystemAdmin'])
                     → <PersonnelImportPage /> (lazy)

/shared-cost-import → RouteGuard(['FinanceAdmin', 'SystemAdmin'])
                      → <SharedCostImportPage /> (lazy)

/admin/cycles      → RouteGuard(['FinanceAdmin', 'SystemAdmin'])
                     → <CycleAdminPage /> (lazy)

/admin/accounts    → RouteGuard(['FinanceAdmin', 'SystemAdmin'])
                     → <AccountMasterPage /> (lazy)

/admin/org-units   → RouteGuard(['SystemAdmin'])
                     → <OrgTreePage /> (lazy)

/admin/users       → RouteGuard(['SystemAdmin'])
                     → <UserAdminPage /> (lazy)

/audit             → RouteGuard(['ITSecurityAuditor', 'SystemAdmin'])
                     → <AuditLogPage /> (lazy)
```

All lazy page components are wrapped in `<Suspense fallback={<PageLoader />}>` where `PageLoader` is a centered Mantine `Loader`.

## Auth Init in Router

`AppRouter` calls `useAuthStore().fetchUser()` on mount (in a `useEffect` with empty dependency array) to initialize auth state from `GET /auth/me`. This runs once per app load and ensures `isAuthenticated` is populated before `RouteGuard` components evaluate.

```typescript
useEffect(() => {
  if (!isAuthenticated && !isLoading) {
    fetchUser();
  }
}, []);
```

## Side-Effects
- On mount: calls `useAuthStore().fetchUser()` once to derive auth state from cookies.
- `React.lazy()` dynamically imports page bundles on first navigation.

## Gotchas
- The `ShellLayout` route must use the React Router `<Outlet />` pattern (parent route with `element={<ShellLayout />}` and nested child routes).
- Lazy loading: all page components should be `React.lazy(() => import(...))`. This requires that each page file has a default export.
- Route paths must use kebab-case (architecture §3 naming convention).
- The `RouteGuard` `roles` prop must EXACTLY match the backend `require_role(...)` calls. Drift between frontend and backend RBAC is a security issue (FCR-002 final-gate check).
- `CompanyReviewer` (0000公司) has access to `/reports` and `/dashboard` but the `DashboardPage` itself filters its content based on role (showing reports link only, no items list per PRD §8.2 and build-plan notes).
- Do NOT add `index.ts` barrel exports to the routes directory.

## Tests
1. **Public routes:** `/`, `/403`, and an unknown path all render without requiring authentication.
2. **Protected route redirects unauthenticated:** Navigating to `/dashboard` when `isAuthenticated: false` redirects to `/` (via `RouteGuard`).
3. **Protected route renders for authorized role:** Navigating to `/dashboard` with `FinanceAdmin` auth state renders `DashboardPage`.
4. **Protected route returns 403 for wrong role:** Navigating to `/admin/users` with `FinanceAdmin` auth state redirects to `/403`.
5. **Route path coverage:** All 10 protected routes exist in the router config (assertion via `getAllByRole` on rendered nav or route matching).

## Consistency Constraints
FCR-002: This page component is wrapped in `<RouteGuard roles={[...exact roles from PRD section 5...]}>`. The route appears in the sidebar only for those roles.
FCR-004: All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
FCR-013: Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
