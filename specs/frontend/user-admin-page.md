# Spec: User Admin Page (`/admin/users`)

**Sub-batch:** 8a (simple)

---

```
Module:    frontend/src/pages/admin/UserAdminPage.tsx
Test path: frontend/tests/unit/pages/admin/UserAdminPage.test.tsx
API module:  frontend/src/api/admin.ts
Hook:      frontend/src/features/cycles/useUsers.ts
FRs:       FR-022
Exports:   UserAdminPage, useUsers
Imports:
  api/admin.ts: listUsers, patchUser, deactivateUser
  components/DataTable.tsx: DataTable
  components/ErrorDisplay.tsx: ErrorDisplay
  i18n: useTranslation
API:
  GET /admin/users?page=&size= — paginated user list; response: { items: UserRead[], total, page, size }
  PATCH /admin/users/{user_id} — update roles and/or org_unit_id; body: { roles?: string[], org_unit_id?: UUID }
  POST /admin/users/{user_id}/deactivate — deactivate user; response: UserRead
Tests:
  1. Renders paginated user table with columns (name, roles, org_unit_id, is_active) on success.
  2. PATCH roles form: selecting a new role set and submitting calls patchUser and updates row optimistically.
  3. "停用帳號" button triggers deactivateUser mutation; shows confirmation dialog before calling POST /admin/users/{id}/deactivate.
  4. Shows ErrorDisplay on RBAC_001 (403) when non-SystemAdmin accesses page.
  5. Pagination controls change page param and refetch list.
Constraints: FCR-001, FCR-002, FCR-004, FCR-005, FCR-009, FCR-010, FCR-013
Gotchas:
  - Route guard: roles=["SystemAdmin"] ONLY. No other role may access this page.
  - FR-022: 403 on access attempt by non-SystemAdmin is logged server-side and redirected to ForbiddenPage on frontend.
  - Destructive op (deactivate) requires confirmation dialog per PRD §8.2 design notes ("破壞性操作須二次確認").
  - `roles` is a string[] — values are role enum strings (e.g. "FinanceAdmin", "HRAdmin"). Display in English.
  - Backend does NOT support local account creation (FR-021); this page only manages existing SSO-sourced users.
  - Default page size: 50; max 200 per architecture pagination convention.
```
