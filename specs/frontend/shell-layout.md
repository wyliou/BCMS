# Spec: Shell Layout with Role-Differentiated Nav (moderate)

Module: `frontend/src/components/ShellLayout.tsx` | Tests: `frontend/tests/unit/components/ShellLayout.test.tsx`

## FRs
- **FR-022:** Role-based data visibility. Sidebar navigation items are conditionally rendered per the PRD §8.2 role table. Users only see nav items for routes they can access.
- **FR-021:** Header displays `user.display_name` and a logout button. On logout, auth store clears state and navigates to `/`.

## Exports
- `ShellLayout` — React component: Mantine `AppShell` with a role-differentiated sidebar, header with user info + logout button, and an `<Outlet />` for page content.

## Imports
- `@mantine/core`: `AppShell`, `NavLink`, `Group`, `Text`, `Button`, `Avatar`, `Burger`, `useMantineTheme`
- `@mantine/hooks`: `useDisclosure`
- `react-router-dom`: `NavLink as RouterNavLink`, `Outlet`, `useNavigate`
- `react-i18next`: `useTranslation`
- `../stores/auth-store`: `useAuthStore`

## Role → Nav Items Mapping (PRD §8.2, §5 Roles)

| Role | Nav Items Shown |
|---|---|
| `FilingUnitManager` | Upload (`/upload`) |
| `FinanceAdmin` | Dashboard, Reports, Shared Cost Import, Cycle Admin, Account Master, Org Tree |
| `HRAdmin` | Personnel Import |
| `UplineReviewer` | Dashboard, Reports |
| `CompanyReviewer` | Reports only |
| `SystemAdmin` | All admin pages (Dashboard, Reports, Cycle Admin, Account Master, Org Tree, User Admin) + Shared Cost Import + Personnel Import |
| `ITSecurityAuditor` | Audit Log |

Nav items are rendered by calling `useAuthStore().hasAnyRole(...)` for each item:

```typescript
const NAV_ITEMS = [
  {
    label: 'nav.dashboard',
    to: '/dashboard',
    roles: ['FinanceAdmin', 'UplineReviewer', 'CompanyReviewer', 'SystemAdmin'],
  },
  {
    label: 'nav.reports',
    to: '/reports',
    roles: ['FinanceAdmin', 'UplineReviewer', 'CompanyReviewer', 'SystemAdmin'],
  },
  {
    label: 'nav.upload',
    to: '/upload',
    roles: ['FilingUnitManager'],
  },
  {
    label: 'nav.personnel_import',
    to: '/personnel-import',
    roles: ['HRAdmin', 'SystemAdmin'],
  },
  {
    label: 'nav.shared_cost_import',
    to: '/shared-cost-import',
    roles: ['FinanceAdmin', 'SystemAdmin'],
  },
  {
    label: 'nav.cycle_admin',
    to: '/admin/cycles',
    roles: ['FinanceAdmin', 'SystemAdmin'],
  },
  {
    label: 'nav.account_master',
    to: '/admin/accounts',
    roles: ['FinanceAdmin', 'SystemAdmin'],
  },
  {
    label: 'nav.org_tree',
    to: '/admin/org-units',
    roles: ['SystemAdmin'],
  },
  {
    label: 'nav.user_admin',
    to: '/admin/users',
    roles: ['SystemAdmin'],
  },
  {
    label: 'nav.audit_log',
    to: '/audit',
    roles: ['ITSecurityAuditor', 'SystemAdmin'],
  },
] as const;
```

A nav item is rendered if `hasAnyRole(...item.roles)` returns `true`.

## Side-Effects
- On logout button click: calls `useAuthStore().logout()` which calls `POST /auth/logout` and navigates to `/`.
- `fetchUser()` from auth store is called once on mount if `user` is null and `isLoading` is false (to handle page refresh).

## Gotchas
- The `AppShell` navbar must be collapsible on mobile (`Burger` toggle + `useDisclosure`). Intranet primarily desktop but Mantine's responsive AppShell handles this.
- Nav item active state: use React Router's `NavLink` `isActive` prop to apply active styling.
- `Outlet` must be rendered inside `AppShell.Main` for page content.
- `theme.other.surfaceBase` color must be applied to `AppShell.Main` background.
- User display name: show `user?.display_name ?? ''`. If user is null (shouldn't happen inside authenticated shell), the header degrades gracefully.
- `CompanyReviewer` gets Reports nav only — no dashboard items list (per PRD §8.2).

## Tests
1. **FinanceAdmin nav:** When auth state has role `FinanceAdmin`, renders nav items for Dashboard, Reports, Shared Cost Import, Cycle Admin, Account Master, Org Tree. Does NOT render Upload or User Admin.
2. **FilingUnitManager nav:** Only Upload nav item is visible; all admin items hidden.
3. **HRAdmin nav:** Only Personnel Import visible.
4. **ITSecurityAuditor nav:** Only Audit Log visible.
5. **Logout button:** Clicking logout calls auth store `logout()`.

## Consistency Constraints
FCR-002: This page component is wrapped in `<RouteGuard roles={[...exact roles from PRD section 5...]}>`. The route appears in the sidebar only for those roles.
FCR-003: This component references status colors via the theme object (e.g., `theme.colors.statusUploaded`). No hardcoded hex color strings for status indicators.
FCR-004: All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
FCR-007: Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
