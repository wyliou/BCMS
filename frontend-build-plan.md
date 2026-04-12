# BCMS Frontend Build Plan

## 1. Build Config (Frontend)

| Key | Value |
|---|---|
| `language` | TypeScript 5.6 |
| `package_manager` | pnpm |
| `test_command` | `pnpm test` |
| `lint_command` | `pnpm lint` |
| `type_check_command` | `pnpm exec tsc --noEmit` |
| `format_command` | `pnpm exec prettier --write src/` |
| `format_check_command` | `pnpm exec prettier --check src/` |
| `build_command` | `pnpm build` |
| `dev_command` | `pnpm dev` |
| `src_dir` | `frontend/src/` |
| `test_dir` | `frontend/tests/` |
| `stub_detection_pattern` | `TODO:\|FIXME:\|throw new Error\(.*not implemented\|\/\/ stub` |

## 2. Gate Configuration (Frontend)

| Gate | Enabled | Command |
|---|---|---|
| `lint` | yes | `pnpm lint` |
| `type_check` | yes | `pnpm exec tsc --noEmit` |
| `format_check` | yes | `pnpm exec prettier --check src/` |
| `unit_tests` | yes | `pnpm test` |
| `build` | yes | `pnpm build` |
| `e2e_tests` | deferred (Batch 9 or later) | `pnpm exec playwright test` |

## 3. Frontend Project Summary

- **Stack:** TypeScript 5.6 + React 18.3 + Vite 5.4 + React Router 6.28 + TanStack Query 5 + Zustand 5 + Mantine 7 + react-hook-form 7 + zod 3.23 + axios 1.7 + react-i18next 15 + Vitest 2 + React Testing Library 16 + ESLint 9 + Prettier 3
- **Package manager:** pnpm 9
- **Backend API base URL:** `VITE_API_BASE_URL` (defaults to `/api/v1` in dev proxy)
- **Auth mechanism:** Cookie-based SSO. Browser never sees the JWT. Auth state derived from `GET /api/v1/auth/me`. Session cookie `bc_session` is HttpOnly/Secure/SameSite=Strict. Refresh via `POST /api/v1/auth/refresh`. Logout via `POST /api/v1/auth/logout`.
- **CSRF:** Double-submit cookie pattern. Server sets `bc_csrf` cookie (readable by JS). Frontend reads it and mirrors the value into `X-CSRF-Token` header on every state-changing request (POST/PATCH/DELETE).
- **Design tokens (PRD section 8.1):**
  - `brand-primary`: `#1B4F8A` (main visual)
  - `brand-secondary`: `#2D7DD2` (interactive elements, links)
  - `surface-base`: `#F4F6F9` (page background)
  - `status-not-uploaded`: `#6B7280` (grey)
  - `status-uploaded`: `#16A34A` (green)
  - `status-resubmit`: `#D97706` (amber)
  - `status-overdue`: `#DC2626` (red)
- **i18n:** zh-TW primary language. English for technical labels (role names, field codes). All user-visible strings in `src/i18n/zh-TW.json`.
- **Role-differentiated navigation (PRD section 8.2):**

| Role | Nav Items | Design Notes |
|---|---|---|
| FilingUnitManager | Upload page | Minimal: download, fill, upload |
| FinanceAdmin | Dashboard, Reports, Shared Cost Import, Cycle Admin, Account Master, Org Tree | Full admin nav |
| HRAdmin | Personnel Import | Import + version history only |
| UplineReviewer | Dashboard, Reports | Read-only + resubmit trigger |
| CompanyReviewer (0000) | Reports only | No upload, no dashboard items list |
| SystemAdmin | All admin pages + Cycle Admin + Org Tree + Account Master + User Admin | Destructive ops require confirmation |
| ITSecurityAuditor | Audit Log Search | No write entry points |

## 4. API Surface Map

### 4.1 Auth (`/auth`)

| Method | Path | Request | Response | Frontend Page |
|---|---|---|---|---|
| GET | `/auth/sso/login?return_to={path}` | query: `return_to` | 302 redirect to IdP | SSO Login Landing |
| GET | `/auth/sso/callback?code=&state=` | query: `code`, `state` | 302 redirect with cookies set | (handled by browser redirect) |
| POST | `/auth/refresh` | (no body; reads `bc_refresh` cookie) | 204 with fresh cookies | axios interceptor (transparent) |
| POST | `/auth/logout` | (no body) | 204 clears cookies | All pages (nav logout button) |
| GET | `/auth/me` | (no body) | `{ user_id: UUID, role: string|null, roles: string[], org_unit_id: UUID|null, display_name: string }` | Auth store init, shell layout |

### 4.2 Cycles (`/cycles`)

| Method | Path | Request | Response | Frontend Page |
|---|---|---|---|---|
| POST | `/cycles` | `{ fiscal_year: int, deadline: date, reporting_currency: string }` | 201 `CycleRead { id, fiscal_year, deadline, reporting_currency, status, opened_at?, closed_at?, reopened_at? }` | Cycle Admin |
| GET | `/cycles` | query: `?fiscal_year=` | `CycleRead[]` | Cycle Admin, Dashboard (cycle selector) |
| GET | `/cycles/{cycle_id}` | — | `CycleRead` | Cycle Admin |
| POST | `/cycles/{cycle_id}/open` | — | `OpenCycleResponse { cycle: CycleSnapshot, transition, generation_summary: { total, generated, errors, error_details[] }, dispatch_summary: { total_recipients, sent, errors } }` | Cycle Admin |
| POST | `/cycles/{cycle_id}/close` | — | `CycleRead` | Cycle Admin |
| POST | `/cycles/{cycle_id}/reopen` | `{ reason: string }` | `CycleRead` | Cycle Admin |
| PATCH | `/cycles/{cycle_id}/reminders` | `{ days_before: int[] }` | `ReminderScheduleRead[]` | Cycle Admin |
| GET | `/cycles/{cycle_id}/filing-units` | — | `FilingUnitInfoRead[] { org_unit_id, code, name, has_manager, excluded, warnings[] }` | Cycle Admin (pre-open check) |

### 4.3 Accounts (`/accounts`)

| Method | Path | Request | Response | Frontend Page |
|---|---|---|---|---|
| GET | `/accounts` | query: `?category=operational\|personnel\|shared_cost` | `AccountCodeRead[]` | Account Master |
| GET | `/accounts/{code}` | — | `AccountCodeRead` | Account Master |
| POST | `/accounts` | `{ code, name, category, level }` | 201 `AccountCodeRead` | Account Master |
| POST | `/cycles/{cycle_id}/actuals` | multipart `file` (CSV/XLSX) | `ImportSummary` | Account Master |

### 4.4 Templates (`/cycles/{cycle_id}/templates`)

| Method | Path | Request | Response | Frontend Page |
|---|---|---|---|---|
| POST | `/cycles/{cycle_id}/templates/{org_unit_id}/regenerate` | — | `TemplateGenerationResult { org_unit_id, status, error? }` | Cycle Admin (error retry) |
| GET | `/cycles/{cycle_id}/templates/{org_unit_id}/download` | — | binary `.xlsx` (Content-Disposition: attachment) | Filing-Unit Upload |

### 4.5 Budget Uploads (`/cycles/{cycle_id}/uploads`)

| Method | Path | Request | Response | Frontend Page |
|---|---|---|---|---|
| POST | `/cycles/{cycle_id}/uploads/{org_unit_id}` | multipart `file` (.xlsx, <=10MB) | 201 `BudgetUploadRead { id, cycle_id, org_unit_id, version, uploader_id, row_count, file_size_bytes, status, uploaded_at }` | Filing-Unit Upload |
| GET | `/cycles/{cycle_id}/uploads/{org_unit_id}` | — | `BudgetUploadRead[]` | Filing-Unit Upload (version history) |
| GET | `/uploads/{upload_id}` | — | `BudgetUploadRead` | Filing-Unit Upload |

### 4.6 Personnel Imports (`/cycles/{cycle_id}/personnel-imports`)

| Method | Path | Request | Response | Frontend Page |
|---|---|---|---|---|
| POST | `/cycles/{cycle_id}/personnel-imports` | multipart `file` (CSV/XLSX) | 201 `PersonnelImportRead { id, cycle_id, uploader_user_id, uploaded_at, filename, file_hash, version, affected_org_units_summary }` | HR Personnel Import |
| GET | `/cycles/{cycle_id}/personnel-imports` | — | `PersonnelImportRead[]` | HR Personnel Import |
| GET | `/personnel-imports/{id}` | — | `PersonnelImportRead` | HR Personnel Import |

### 4.7 Shared Cost Imports (`/cycles/{cycle_id}/shared-cost-imports`)

| Method | Path | Request | Response | Frontend Page |
|---|---|---|---|---|
| POST | `/cycles/{cycle_id}/shared-cost-imports` | multipart `file` (CSV/XLSX) | 201 `SharedCostUploadRead { id, cycle_id, uploader_user_id, uploaded_at, filename, version, affected_org_units_summary }` | Shared Cost Import |
| GET | `/cycles/{cycle_id}/shared-cost-imports` | — | `SharedCostUploadRead[]` | Shared Cost Import |
| GET | `/shared-cost-imports/{upload_id}` | — | `SharedCostUploadRead` | Shared Cost Import |

### 4.8 Dashboard (`/cycles/{cycle_id}/dashboard`)

| Method | Path | Request | Response | Frontend Page |
|---|---|---|---|---|
| GET | `/cycles/{cycle_id}/dashboard` | query: `?status=&org_unit_id=&limit=&offset=` | `DashboardResponse { cycle: {...}, items: DashboardItem[] { org_unit_id, org_unit_name, status, last_uploaded_at?, version? }, summary: { total, uploaded, not_downloaded, downloaded, resubmit_requested }, data_freshness: { snapshot_at, stale } }` | Dashboard |

### 4.9 Consolidated Reports (`/cycles/{cycle_id}/reports`)

| Method | Path | Request | Response | Frontend Page |
|---|---|---|---|---|
| GET | `/cycles/{cycle_id}/reports/consolidated` | — | `ConsolidatedReport { cycle_id, rows: ConsolidatedReportRow[] { org_unit_id, org_unit_name, account_code, account_name, actual?, operational_budget?, personnel_budget?, shared_cost?, delta_amount?, delta_pct, budget_status }, reporting_currency, budget_last_updated_at?, personnel_last_updated_at?, shared_cost_last_updated_at? }` | Consolidated Report |
| POST | `/cycles/{cycle_id}/reports/exports` | query: `?format=xlsx\|csv` | 201 `{ mode: "sync", file_url, expires_at }` or 202 `{ mode: "async", job_id }` | Consolidated Report |
| GET | `/exports/{job_id}` | — | `{ status, result?, error_message? }` | Consolidated Report (export polling) |
| GET | `/exports/{job_id}/file` | — | binary file download | Consolidated Report |

### 4.10 Notifications & Resubmit

| Method | Path | Request | Response | Frontend Page |
|---|---|---|---|---|
| GET | `/notifications/failed` | — | `{ items: FailedNotificationItem[] { id, type, recipient_id, status, bounce_reason?, created_at } }` | Dashboard (admin view) |
| POST | `/notifications/{id}/resend` | `{ recipient_email: string }` | `{ id, status, bounce_reason? }` | Dashboard (admin view) |
| POST | `/resubmit-requests` | `{ cycle_id, org_unit_id, reason, target_version?, requester_user_id, recipient_user_id, recipient_email }` | 201 `ResubmitRequestRead { id, cycle_id, org_unit_id, requester_id, target_version?, reason, requested_at }` | Dashboard (resubmit modal) |
| GET | `/resubmit-requests` | query: `?cycle_id=&org_unit_id=` | `ResubmitRequestRead[]` | Dashboard (resubmit history) |

### 4.11 Audit Logs (`/audit-logs`)

| Method | Path | Request | Response | Frontend Page |
|---|---|---|---|---|
| GET | `/audit-logs` | query: `?user_id=&action=&resource_type=&resource_id=&from=&to=&page=&size=` | `{ items: AuditLogRead[], total, page, size }` | Audit Log Search |
| GET | `/audit-logs/verify` | query: `?from=&to=` | `{ verified: bool, range: [datetime?, datetime?], chain_length: int }` | Audit Log Search |
| GET | `/audit-logs/export` | query: `?from=&to=` | CSV file download (streaming) | Audit Log Search |

### 4.12 Admin

| Method | Path | Request | Response | Frontend Page |
|---|---|---|---|---|
| GET | `/admin/org-units` | — | `OrgUnitRead[] { id, code, name, level_code, parent_id?, is_filing_unit, is_reviewer_only, excluded_for_cycle_ids[] }` | Org Tree Admin |
| PATCH | `/admin/org-units/{id}` | `{ excluded_for_cycle_ids?: string[] }` | `OrgUnitRead` | Org Tree Admin |
| GET | `/admin/users` | query: `?page=&size=` | `{ items: UserRead[] { id, name, roles[], org_unit_id?, is_active }, total, page, size }` | User Admin (SystemAdmin only) |
| PATCH | `/admin/users/{user_id}` | `{ roles?: string[], org_unit_id?: UUID }` | `UserRead` | User Admin |
| POST | `/admin/users/{user_id}/deactivate` | — | `UserRead` | User Admin |

## 5. Shared Utilities

### 5.1 API Client (`src/api/client.ts`)

- **Purpose:** Configured axios instance with cookie auth + CSRF interceptor + 401 refresh
- **Interface:**
  ```typescript
  const apiClient: AxiosInstance; // withCredentials: true, baseURL from VITE_API_BASE_URL
  // Request interceptor: reads bc_csrf cookie, sets X-CSRF-Token header on POST/PATCH/DELETE
  // Response interceptor: on 401 -> POST /auth/refresh -> retry original; on refresh fail -> redirect to /auth/sso/login
- **Placement:** `frontend/src/api/client.ts`
- **Consumers:** Every API module

### 5.2 API Resource Modules (`src/api/*.ts`)

One file per resource group, typed with zod schemas:
- `src/api/auth.ts` — `fetchMe()`, `logout()`, `refresh()`
- `src/api/cycles.ts` — `listCycles()`, `getCycle()`, `createCycle()`, `openCycle()`, `closeCycle()`, `reopenCycle()`, `setReminders()`, `getFilingUnits()`
- `src/api/accounts.ts` — `listAccounts()`, `upsertAccount()`, `importActuals()`
- `src/api/templates.ts` — `downloadTemplate()`, `regenerateTemplate()`
- `src/api/budget-uploads.ts` — `uploadBudget()`, `listUploadVersions()`, `getUpload()`
- `src/api/personnel.ts` — `importPersonnel()`, `listPersonnelVersions()`, `getPersonnelImport()`
- `src/api/shared-costs.ts` — `importSharedCosts()`, `listSharedCostVersions()`, `getSharedCostImport()`
- `src/api/dashboard.ts` — `getDashboard()`
- `src/api/reports.ts` — `getConsolidatedReport()`, `startExport()`, `getExportStatus()`, `downloadExport()`
- `src/api/notifications.ts` — `listFailedNotifications()`, `resendNotification()`, `createResubmitRequest()`, `listResubmitRequests()`
- `src/api/audit.ts` — `queryAuditLogs()`, `verifyChain()`, `exportAuditLogs()`
- `src/api/admin.ts` — `listOrgUnits()`, `patchOrgUnit()`, `listUsers()`, `patchUser()`, `deactivateUser()`

### 5.3 TanStack Query Provider (`src/providers/QueryProvider.tsx`)

- **Purpose:** QueryClientProvider with default options (staleTime, retry, error handling)
- **Placement:** `frontend/src/providers/QueryProvider.tsx`
- **Consumers:** `App.tsx` wraps the entire app

### 5.4 Auth Store (`src/stores/auth-store.ts`)

- **Purpose:** Zustand store holding auth state derived from `/auth/me`
- **Interface:**
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
- **Placement:** `frontend/src/stores/auth-store.ts`
- **Consumers:** Route guards, shell layout, every page that checks role

### 5.5 RBAC Navigation Guard (`src/components/RouteGuard.tsx`)

- **Purpose:** React component that checks auth store for required roles before rendering children; redirects to login or 403 page
- **Interface:** `<RouteGuard roles={["FinanceAdmin", "SystemAdmin"]}>{children}</RouteGuard>`
- **Placement:** `frontend/src/components/RouteGuard.tsx`
- **Consumers:** Every protected route in `routes/`

### 5.6 i18n Setup (`src/i18n/index.ts` + `src/i18n/zh-TW.json`)

- **Purpose:** react-i18next init with zh-TW as default language
- **Placement:** `frontend/src/i18n/index.ts`, `frontend/src/i18n/zh-TW.json`
- **Consumers:** Every component via `useTranslation()` hook

### 5.7 Error Display Component (`src/components/ErrorDisplay.tsx`)

- **Purpose:** Renders API error envelope (`error.code` + `error.message` + `error.details[]`) in a Mantine Alert. Handles batch validation row-level errors as a collapsible table.
- **Interface:** `<ErrorDisplay error={apiError} />`
- **Placement:** `frontend/src/components/ErrorDisplay.tsx`
- **Consumers:** Upload page, import pages, cycle admin, any form page

### 5.8 Status Badge (`src/components/StatusBadge.tsx`)

- **Purpose:** Renders a Mantine Badge with the correct status color from design tokens
- **Interface:** `<StatusBadge status="uploaded" />` — maps status string to design token color
- **Placement:** `frontend/src/components/StatusBadge.tsx`
- **Consumers:** Dashboard, Filing-Unit Upload

### 5.9 File Download Helper (`src/lib/download.ts`)

- **Purpose:** Handles both sync (blob response) and async (job_id polling) download patterns
- **Interface:**
  ```typescript
  function downloadBlob(url: string, filename: string): Promise<void>;
  function pollAndDownload(jobId: string, pollUrl: string, fileUrl: string): Promise<void>;
  ```
- **Placement:** `frontend/src/lib/download.ts`
- **Consumers:** Template download, export download, audit log export

### 5.10 DataTable Wrapper (`src/components/DataTable.tsx`)

- **Purpose:** Thin wrapper around Mantine Table or TanStack Table for consistent pagination, sorting, empty states
- **Placement:** `frontend/src/components/DataTable.tsx`
- **Consumers:** Dashboard, Audit Log, version history lists

### 5.11 Shell Layout (`src/components/ShellLayout.tsx`)

- **Purpose:** AppShell with role-based sidebar navigation per PRD section 8.2, header with user info + logout
- **Placement:** `frontend/src/components/ShellLayout.tsx`
- **Consumers:** `App.tsx` as the root layout

## 6. Batch Plan

### Batch 7 — Frontend Foundation

**Goal:** Scaffold the frontend project, establish all shared infrastructure, and create a working authenticated shell with role-based routing.

| Item | Path | Test Path | Complexity |
|---|---|---|---|
| Vite + React 18.3 + React Router 6 scaffold | `frontend/` root files (`package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`) | n/a | simple |
| ESLint 9 + Prettier 3 config | `frontend/.eslintrc.cjs`, `frontend/.prettierrc` | n/a | simple |
| Mantine 7 theme with PRD section 8.1 design tokens | `frontend/src/styles/theme.ts` | `frontend/tests/unit/styles/theme.test.ts` | simple |
| i18n setup (react-i18next, zh-TW) | `frontend/src/i18n/index.ts`, `frontend/src/i18n/zh-TW.json` | `frontend/tests/unit/i18n/i18n.test.ts` | simple |
| Axios API client with cookie auth + CSRF interceptor | `frontend/src/api/client.ts` | `frontend/tests/unit/api/client.test.ts` | moderate |
| TanStack Query provider | `frontend/src/providers/QueryProvider.tsx` | `frontend/tests/unit/providers/QueryProvider.test.tsx` | simple |
| Auth API module (`fetchMe`, `logout`, `refresh`) | `frontend/src/api/auth.ts` | `frontend/tests/unit/api/auth.test.ts` | simple |
| Zustand auth store + `/auth/me` integration | `frontend/src/stores/auth-store.ts` | `frontend/tests/unit/stores/auth-store.test.ts` | moderate |
| RouteGuard component | `frontend/src/components/RouteGuard.tsx` | `frontend/tests/unit/components/RouteGuard.test.tsx` | moderate |
| Shell layout (sidebar/nav per role from PRD section 8.2) | `frontend/src/components/ShellLayout.tsx` | `frontend/tests/unit/components/ShellLayout.test.tsx` | moderate |
| React Router config with role-guarded routes | `frontend/src/routes/index.tsx` | `frontend/tests/unit/routes/routes.test.tsx` | moderate |
| SSO Login Landing page | `frontend/src/pages/auth/LoginPage.tsx` | `frontend/tests/unit/pages/auth/LoginPage.test.tsx` | simple |
| 403 Forbidden page | `frontend/src/pages/errors/ForbiddenPage.tsx` | `frontend/tests/unit/pages/errors/ForbiddenPage.test.tsx` | simple |
| 404 Not Found page | `frontend/src/pages/errors/NotFoundPage.tsx` | `frontend/tests/unit/pages/errors/NotFoundPage.test.tsx` | simple |
| ErrorBoundary component | `frontend/src/components/ErrorBoundary.tsx` | `frontend/tests/unit/components/ErrorBoundary.test.tsx` | simple |
| ErrorDisplay component | `frontend/src/components/ErrorDisplay.tsx` | `frontend/tests/unit/components/ErrorDisplay.test.tsx` | moderate |
| StatusBadge component | `frontend/src/components/StatusBadge.tsx` | `frontend/tests/unit/components/StatusBadge.test.tsx` | simple |
| File download helper | `frontend/src/lib/download.ts` | `frontend/tests/unit/lib/download.test.ts` | moderate |
| DataTable wrapper | `frontend/src/components/DataTable.tsx` | `frontend/tests/unit/components/DataTable.test.tsx` | moderate |
| Vitest setup with React Testing Library | `frontend/vitest.config.ts`, `frontend/tests/setup.ts` | n/a | simple |
| App.tsx entry point wiring all providers | `frontend/src/App.tsx` | `frontend/tests/unit/App.test.tsx` | simple |

**Exports (Batch 7)**

| Symbol | Module | Consumers |
|---|---|---|
| `apiClient` | `api/client.ts` | every API module |
| `useAuthStore` | `stores/auth-store.ts` | RouteGuard, ShellLayout, all pages |
| `RouteGuard` | `components/RouteGuard.tsx` | `routes/index.tsx` |
| `ShellLayout` | `components/ShellLayout.tsx` | `App.tsx` |
| `ErrorDisplay` | `components/ErrorDisplay.tsx` | all form pages |
| `StatusBadge` | `components/StatusBadge.tsx` | Dashboard, Upload page |
| `downloadBlob`, `pollAndDownload` | `lib/download.ts` | Template download, Export download |
| `DataTable` | `components/DataTable.tsx` | Dashboard, Audit, version lists |
| `theme` | `styles/theme.ts` | MantineProvider in `App.tsx` |
| `i18n` | `i18n/index.ts` | I18nextProvider in `App.tsx` |

**Gate checks:** lint, type_check, format_check, unit_tests (Vitest), build (Vite).

---

### Batch 8 — Feature Pages

**Goal:** Implement all 11 pages from architecture section 5.13. Grouped into sub-batches by complexity for parallelization.

#### Sub-batch 8a — Simple Pages (parallelizable)

**SSO Login Landing** (`/`)

| Key | Value |
|---|---|
| Path | `frontend/src/pages/auth/LoginPage.tsx` |
| Test path | `frontend/tests/unit/pages/auth/LoginPage.test.tsx` |
| FRs | FR-021 |
| Exports | `LoginPage` |
| Imports | `api/auth.ts` (`fetchMe`), `stores/auth-store.ts`, i18n |
| Complexity | simple |

**Audit Log Search** (`/audit`)

| Key | Value |
|---|---|
| Path | `frontend/src/pages/audit/AuditLogPage.tsx` |
| Test path | `frontend/tests/unit/pages/audit/AuditLogPage.test.tsx` |
| API module | `frontend/src/api/audit.ts` |
| Hook | `frontend/src/features/audit/useAuditLogs.ts` |
| FRs | FR-023 |
| Exports | `AuditLogPage`, `useAuditLogs` |
| Imports | `api/audit.ts`, `components/DataTable.tsx`, `lib/download.ts`, i18n |
| Complexity | simple |

**Org Tree Admin** (`/admin/org-units`)

| Key | Value |
|---|---|
| Path | `frontend/src/pages/admin/OrgTreePage.tsx` |
| Test path | `frontend/tests/unit/pages/admin/OrgTreePage.test.tsx` |
| API module | `frontend/src/api/admin.ts` |
| Hook | `frontend/src/features/cycles/useOrgUnits.ts` |
| FRs | FR-002 |
| Exports | `OrgTreePage`, `useOrgUnits` |
| Imports | `api/admin.ts`, `components/DataTable.tsx`, i18n |
| Complexity | simple |

**Account Master** (`/admin/accounts`)

| Key | Value |
|---|---|
| Path | `frontend/src/pages/admin/AccountMasterPage.tsx` |
| Test path | `frontend/tests/unit/pages/admin/AccountMasterPage.test.tsx` |
| API module | `frontend/src/api/accounts.ts` |
| Hook | `frontend/src/features/cycles/useAccounts.ts` |
| FRs | FR-007, FR-008 |
| Exports | `AccountMasterPage`, `useAccounts` |
| Imports | `api/accounts.ts`, `components/DataTable.tsx`, `components/ErrorDisplay.tsx`, i18n |
| Complexity | simple |

**User Admin** (`/admin/users`)

| Key | Value |
|---|---|
| Path | `frontend/src/pages/admin/UserAdminPage.tsx` |
| Test path | `frontend/tests/unit/pages/admin/UserAdminPage.test.tsx` |
| API module | `frontend/src/api/admin.ts` |
| Hook | `frontend/src/features/cycles/useUsers.ts` |
| FRs | FR-022 |
| Exports | `UserAdminPage`, `useUsers` |
| Imports | `api/admin.ts`, `components/DataTable.tsx`, `components/ErrorDisplay.tsx`, i18n |
| Complexity | simple |

#### Sub-batch 8b — Moderate Pages (parallelizable)

**Cycle Admin** (`/admin/cycles`)

| Key | Value |
|---|---|
| Path | `frontend/src/pages/admin/CycleAdminPage.tsx` |
| Test path | `frontend/tests/unit/pages/admin/CycleAdminPage.test.tsx` |
| API module | `frontend/src/api/cycles.ts` |
| Hook | `frontend/src/features/cycles/useCycles.ts` |
| FRs | FR-001, FR-003, FR-005, FR-006 |
| Exports | `CycleAdminPage`, `useCycles` |
| Imports | `api/cycles.ts`, `api/templates.ts`, `components/ErrorDisplay.tsx`, `components/DataTable.tsx`, i18n |
| Complexity | moderate |

**Filing-Unit Upload** (`/upload`)

| Key | Value |
|---|---|
| Path | `frontend/src/pages/upload/UploadPage.tsx` |
| Test path | `frontend/tests/unit/pages/upload/UploadPage.test.tsx` |
| API module | `frontend/src/api/budget-uploads.ts`, `frontend/src/api/templates.ts` |
| Hook | `frontend/src/features/budget-uploads/useBudgetUpload.ts` |
| FRs | FR-010, FR-011, FR-012 |
| Exports | `UploadPage`, `useBudgetUpload` |
| Imports | `api/budget-uploads.ts`, `api/templates.ts`, `stores/auth-store.ts`, `components/ErrorDisplay.tsx`, `components/StatusBadge.tsx`, `lib/download.ts`, i18n |
| Complexity | moderate |

**HR Personnel Import** (`/personnel-import`)

| Key | Value |
|---|---|
| Path | `frontend/src/pages/personnel-import/PersonnelImportPage.tsx` |
| Test path | `frontend/tests/unit/pages/personnel-import/PersonnelImportPage.test.tsx` |
| API module | `frontend/src/api/personnel.ts` |
| Hook | `frontend/src/features/personnel-import/usePersonnelImport.ts` |
| FRs | FR-024, FR-025, FR-026 |
| Exports | `PersonnelImportPage`, `usePersonnelImport` |
| Imports | `api/personnel.ts`, `components/ErrorDisplay.tsx`, `components/DataTable.tsx`, i18n |
| Complexity | moderate |

**Shared Cost Import** (`/shared-cost-import`)

| Key | Value |
|---|---|
| Path | `frontend/src/pages/shared-cost-import/SharedCostImportPage.tsx` |
| Test path | `frontend/tests/unit/pages/shared-cost-import/SharedCostImportPage.test.tsx` |
| API module | `frontend/src/api/shared-costs.ts` |
| Hook | `frontend/src/features/shared-cost-import/useSharedCostImport.ts` |
| FRs | FR-027, FR-028, FR-029 |
| Exports | `SharedCostImportPage`, `useSharedCostImport` |
| Imports | `api/shared-costs.ts`, `components/ErrorDisplay.tsx`, `components/DataTable.tsx`, i18n |
| Complexity | moderate |

**Resubmit Trigger** (modal in Dashboard)

| Key | Value |
|---|---|
| Path | `frontend/src/features/notifications/ResubmitModal.tsx` |
| Test path | `frontend/tests/unit/features/notifications/ResubmitModal.test.tsx` |
| API module | `frontend/src/api/notifications.ts` |
| Hook | `frontend/src/features/notifications/useResubmit.ts` |
| FRs | FR-018, FR-019 |
| Exports | `ResubmitModal`, `useResubmit` |
| Imports | `api/notifications.ts`, `stores/auth-store.ts`, `components/ErrorDisplay.tsx`, i18n |
| Complexity | moderate |

#### Sub-batch 8c — Complex Pages

**Dashboard** (`/dashboard`)

| Key | Value |
|---|---|
| Path | `frontend/src/pages/dashboard/DashboardPage.tsx` |
| Test path | `frontend/tests/unit/pages/dashboard/DashboardPage.test.tsx` |
| API module | `frontend/src/api/dashboard.ts`, `frontend/src/api/notifications.ts` |
| Hook | `frontend/src/features/consolidated-report/useDashboard.ts` |
| FRs | FR-004, FR-014 |
| Exports | `DashboardPage`, `useDashboard` |
| Imports | `api/dashboard.ts`, `api/notifications.ts`, `features/notifications/ResubmitModal.tsx`, `components/StatusBadge.tsx`, `components/DataTable.tsx`, `stores/auth-store.ts`, i18n |
| Notes | TanStack Query `refetchInterval: 5000` with `refetchIntervalInBackground: false` (FCR-006). Shows summary cards + filterable status grid. CompanyReviewer gets report link only, no items. |
| Complexity | complex |

**Consolidated Report** (`/reports`)

| Key | Value |
|---|---|
| Path | `frontend/src/pages/reports/ConsolidatedReportPage.tsx` |
| Test path | `frontend/tests/unit/pages/reports/ConsolidatedReportPage.test.tsx` |
| API module | `frontend/src/api/reports.ts` |
| Hook | `frontend/src/features/consolidated-report/useConsolidatedReport.ts` |
| FRs | FR-015, FR-016, FR-017 |
| Exports | `ConsolidatedReportPage`, `useConsolidatedReport` |
| Imports | `api/reports.ts`, `lib/download.ts`, `components/DataTable.tsx`, `stores/auth-store.ts`, i18n |
| Notes | Three-column-group TanStack Table (operational / personnel / shared_cost). Async export with job polling. `delta_pct` displays "N/A" when actual is 0. `budget_status: "not_uploaded"` displays "未上傳". Currency formatting via `Intl.NumberFormat`. |
| Complexity | complex |

## 7. Ambiguities (Resolved 2026-04-12)

1. **User Admin page scope.** ✅ DECIDED: Yes, build User Admin page at `/admin/users` for SystemAdmin. Backend endpoints exist (GET /admin/users, PATCH /admin/users/{id}, POST /admin/users/{id}/deactivate). Added as simple page in Sub-batch 8a.

2. **Filing-Unit Upload file download for historical versions.** Architecture lists routes not yet wired in backend. **Resolution:** Plan hooks but don't implement until backend endpoints exist. Deferred.

3. **Notification list page.** ✅ DECIDED: Surface failed notifications as a collapsible section within Dashboard for FinanceAdmin. No separate page.

4. **Report export format.** Backend supports `"xlsx"|"csv"` only (not pdf). Frontend matches backend.

5. **Resubmit request route path.** Backend uses flat `POST /resubmit-requests` with body params, not nested path. Frontend API module uses the flat path.

6. **Dashboard cycle selector.** ✅ DECIDED: Auto-select latest Open cycle by default. Dropdown to switch to other cycles (including closed for historical view).

7. **Accounts PATCH.** Backend uses `POST /accounts` as upsert by natural key `code`. Frontend Account Master uses POST for both create and update.

8. **Vite dev proxy.** `vite.config.ts` proxies `/api/v1` to `http://localhost:8000` for cookie-based auth in dev.
```

---