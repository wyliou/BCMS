# BCMS Frontend Consistency Registry

Cross-cutting constraints specific to the frontend build, discovered by scanning PRD v4.3, architecture.md, and the backend API surface. Each entry has a "Stage B check" that spec writers paste into module specs and a "Final-gate check" describing the inspection step.

---

### FCR-001 — Auth cookie transport

- **Category:** security
- **Concern:** Every API call must use `withCredentials: true` on the axios instance and include the `X-CSRF-Token` header (read from the `bc_csrf` cookie) on every state-changing request (POST, PATCH, DELETE). The frontend never stores or reads the `bc_session` or `bc_refresh` cookies directly — they are HttpOnly.
- **Affected modules:** `src/api/client.ts`, every API module in `src/api/`
- **Owner:** `src/api/client.ts`
- **Stage B check:** *"This module uses the shared `apiClient` from `src/api/client.ts` for all HTTP requests. It does NOT create its own axios instance or use raw `fetch()`. The CSRF token is read from `document.cookie` and set as `X-CSRF-Token` by the request interceptor."*
- **Final-gate check:** Grep `fetch\(` and `axios.create\(` across `frontend/src/` (excluding `api/client.ts`); must be empty. Grep `withCredentials` in `api/client.ts`; must be `true`.

### FCR-002 — Role-based visibility

- **Category:** authorization
- **Concern:** Navigation items and route guards must match PRD section 8.2 role table exactly. Each route is wrapped in `<RouteGuard roles={[...]}>` with the correct role set. Sidebar navigation items are conditionally rendered based on `useAuthStore().hasRole(...)`.
- **Affected modules:** `src/routes/index.tsx`, `src/components/ShellLayout.tsx`, `src/components/RouteGuard.tsx`
- **Owner:** `src/routes/index.tsx`
- **Stage B check:** *"This page component is wrapped in `<RouteGuard roles={[...exact roles from PRD section 5...]}>`. The route appears in the sidebar only for those roles."*
- **Final-gate check:** Review each route definition against PRD section 5 role table. Every `RouteGuard` roles prop must match the corresponding backend `require_role(...)` on the consumed API endpoint.

### FCR-003 — Status colors use design tokens

- **Category:** design_consistency
- **Concern:** Status colors (not_uploaded=grey, uploaded=green, resubmit=amber, overdue=red) must use the design tokens defined in PRD section 8.1 via the Mantine theme. Never hardcode hex values in components.
- **Affected modules:** `src/components/StatusBadge.tsx`, `src/pages/dashboard/DashboardPage.tsx`, `src/styles/theme.ts`
- **Owner:** `src/styles/theme.ts` (defines tokens), `src/components/StatusBadge.tsx` (consumes them)
- **Stage B check:** *"This component references status colors via the theme object (e.g., `theme.colors.statusUploaded`) or via StatusBadge. No hardcoded hex color strings for status indicators."*
- **Final-gate check:** Grep `#6B7280|#16A34A|#D97706|#DC2626` across `frontend/src/` excluding `styles/theme.ts`; must be empty.

### FCR-004 — i18n coverage

- **Category:** i18n
- **Concern:** No hardcoded Chinese (or any natural language) strings in React components. All user-facing text uses `t('key')` from `useTranslation()`. The zh-TW JSON file is the single source of all display strings.
- **Affected modules:** every component in `src/pages/` and `src/features/`
- **Owner:** `src/i18n/zh-TW.json`
- **Stage B check:** *"All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX."*
- **Final-gate check:** Grep for CJK character ranges (`[\u4e00-\u9fff]`) in `*.tsx` files under `frontend/src/` (excluding `i18n/` and test files); must be empty.

### FCR-005 — Error display follows shared envelope

- **Category:** error_handling
- **Concern:** All API errors must be parsed and displayed using the shared `ErrorDisplay` component, which understands the backend error envelope format: `{ error: { code, message, details? }, request_id? }`. Row-level validation errors (`details[]` with `row`, `column`, `code`, `reason`) must be displayed as a table.
- **Affected modules:** every page that performs API mutations, `src/components/ErrorDisplay.tsx`
- **Owner:** `src/components/ErrorDisplay.tsx`
- **Stage B check:** *"API errors caught by mutation `onError` callbacks are passed to `<ErrorDisplay error={err} />`. The component is NOT duplicated or reimplemented locally."*
- **Final-gate check:** Grep `catch.*error` and `onError` in page components; verify each references `ErrorDisplay`. No custom error rendering that bypasses the shared component.

### FCR-006 — Polling discipline

- **Category:** performance
- **Concern:** Dashboard polls at 5s intervals via TanStack Query `refetchInterval: 5000`. Polling must stop when the browser tab is hidden (`refetchIntervalInBackground: false`). No other page uses polling unless explicitly required by an FR.
- **Affected modules:** `src/features/consolidated-report/useDashboard.ts`
- **Owner:** `useDashboard.ts`
- **Stage B check:** *"The `useQuery` call for dashboard data sets `refetchInterval: 5000` and `refetchIntervalInBackground: false`. No `setInterval` or manual polling loops."*
- **Final-gate check:** Grep `setInterval` across `frontend/src/`; must be empty (all polling via TanStack Query). Grep `refetchInterval` — must appear only in dashboard hook.

### FCR-007 — WCAG AA compliance

- **Category:** accessibility
- **Concern:** Color contrast at least 4.5:1 for all text. Visible focus indicators on all interactive elements. `aria-describedby` linking form error messages to their input fields. All primary workflows keyboard-navigable.
- **Affected modules:** all components
- **Owner:** `src/styles/theme.ts` (contrast), each form component (aria attributes)
- **Stage B check:** *"Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order."*
- **Final-gate check:** Run `pnpm exec axe-core` or equivalent accessibility audit on rendered pages. Manual check: Tab through each form and verify focus ring visibility.

### FCR-008 — File downloads use shared helper

- **Category:** download_handling
- **Concern:** File downloads must use the shared helper from `src/lib/download.ts`. Two patterns: (1) sync blob download for templates and audit CSV export, (2) async job polling for consolidated report export (POST returns `job_id`, GET polls status, GET downloads file).
- **Affected modules:** `src/pages/upload/UploadPage.tsx` (template download), `src/pages/reports/ConsolidatedReportPage.tsx` (export), `src/pages/audit/AuditLogPage.tsx` (CSV export)
- **Owner:** `src/lib/download.ts`
- **Stage B check:** *"File downloads in this component use `downloadBlob()` or `pollAndDownload()` from `src/lib/download.ts`. No manual `window.open()`, `a.click()`, or direct blob handling."*
- **Final-gate check:** Grep `window.open|createElement.*a.*click|URL.createObjectURL` across `frontend/src/` excluding `lib/download.ts`; must be empty.

### FCR-009 — API response type safety

- **Category:** type_safety
- **Concern:** Every API response must be validated with a zod schema before use. API modules return typed objects, not raw `AxiosResponse.data`. This prevents runtime type errors when the backend changes response shapes.
- **Affected modules:** all files in `src/api/`
- **Owner:** each `src/api/*.ts` file
- **Stage B check:** *"The API function in this module defines a zod schema for the response and calls `.parse()` or `.safeParse()` on `response.data` before returning."*
- **Final-gate check:** Grep `response\.data` in `src/api/` files; each occurrence must be followed by a zod parse call within the same function.

### FCR-010 — Loading, error, and empty state coverage

- **Category:** ux_completeness
- **Concern:** Every page that fetches data must handle three states: loading (skeleton or spinner), error (ErrorDisplay), and empty (descriptive message with action hint). This prevents blank screens and unclear failures.
- **Affected modules:** all page components in `src/pages/`
- **Owner:** each page component
- **Stage B check:** *"This page checks `isLoading`, `isError`, and `data?.length === 0` from its query hook and renders appropriate UI for each state."*
- **Final-gate check:** Review each page component; verify the presence of loading, error, and empty state conditional branches. Unit tests must cover all three states.

### FCR-011 — No credentials in client code

- **Category:** security
- **Concern:** The frontend never stores, reads, or logs JWT tokens, session cookies (they are HttpOnly), or any secret. `localStorage` and `sessionStorage` are never used for auth data. The Zustand auth store holds only the `/auth/me` response (user profile, roles).
- **Affected modules:** `src/stores/auth-store.ts`, `src/api/client.ts`
- **Owner:** `src/stores/auth-store.ts`
- **Stage B check:** *"This module does not read `bc_session` or `bc_refresh` cookies. It does not write to `localStorage` or `sessionStorage` for auth purposes."*
- **Final-gate check:** Grep `localStorage|sessionStorage|bc_session|bc_refresh` across `frontend/src/`; must be empty except for the CSRF cookie read (`bc_csrf`) in `api/client.ts`.

### FCR-012 — Consolidated report three-source display

- **Category:** data_display
- **Concern:** The consolidated report table at 1000-level and above must display three column groups: operational budget, personnel budget, shared cost. Below 1000 level, personnel_budget and shared_cost columns show null (display as "—"). `delta_pct` displays "N/A" when actual is 0. `budget_status: "not_uploaded"` displays "未上傳" (via i18n).
- **Affected modules:** `src/pages/reports/ConsolidatedReportPage.tsx`, `src/features/consolidated-report/useConsolidatedReport.ts`
- **Owner:** `ConsolidatedReportPage.tsx`
- **Stage B check:** *"The report table renders `personnel_budget` and `shared_cost` columns. Null values display '—'. The `delta_pct` column renders the string value directly (backend sends 'N/A' for zero-actual rows). The `budget_status` field 'not_uploaded' is translated to the i18n key `report.status.not_uploaded`."*
- **Final-gate check:** Unit test: render report with mixed rows (some with personnel/shared_cost null, some with delta_pct "N/A", some with budget_status "not_uploaded"); verify correct display text.

### FCR-013 — Environment variable prefix

- **Category:** configuration
- **Concern:** All environment variables consumed by the frontend must be prefixed with `VITE_` per Vite convention. Currently the only defined variable is `VITE_API_BASE_URL`. New variables must follow this pattern.
- **Affected modules:** `frontend/.env`, `frontend/.env.example`, `src/api/client.ts`
- **Owner:** `src/api/client.ts`
- **Stage B check:** *"Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references."*
- **Final-gate check:** Grep `process\.env` across `frontend/src/`; must be empty. Grep `import\.meta\.env\.` — all references must start with `VITE_`.

### FCR-014 — Decimal and currency formatting

- **Category:** data_display
- **Concern:** All monetary amounts from the API arrive as strings (Decimal serialized as string per CR-036). The frontend must parse them carefully and format using `Intl.NumberFormat('zh-TW', { style: 'decimal', minimumFractionDigits: 2 })` or similar. Never use `parseFloat()` for display — use a dedicated format utility to preserve precision.
- **Affected modules:** `src/pages/reports/ConsolidatedReportPage.tsx`, any component displaying amounts
- **Owner:** `src/lib/format-currency.ts`
- **Stage B check:** *"Monetary amounts are formatted via `formatAmount()` from `src/lib/format-currency.ts`. No raw `Number()` or `parseFloat()` for display purposes."*
- **Final-gate check:** Grep `parseFloat|Number\(` in report and dashboard page components; must not be used for display formatting.