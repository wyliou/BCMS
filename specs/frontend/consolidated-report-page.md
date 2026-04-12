# Spec: Consolidated Report Page (`/reports`)

**Sub-batch:** 8c (complex)

---

## Module Metadata

| Key | Value |
|-----|-------|
| Module path | `frontend/src/pages/reports/ConsolidatedReportPage.tsx` |
| Test path | `frontend/tests/unit/pages/reports/ConsolidatedReportPage.test.tsx` |
| API module | `frontend/src/api/reports.ts` |
| Hook | `frontend/src/features/consolidated-report/useConsolidatedReport.ts` |
| FRs | FR-015, FR-016, FR-017 |
| Exports | `ConsolidatedReportPage`, `useConsolidatedReport` |

---

## Imports

| Symbol | Source module |
|--------|--------------|
| `apiClient` | `src/api/client.ts` |
| `getConsolidatedReport`, `startExport`, `getExportStatus`, `downloadExport` | `src/api/reports.ts` |
| `downloadBlob`, `pollAndDownload` | `src/lib/download.ts` |
| `DataTable` | `src/components/DataTable.tsx` |
| `ErrorDisplay` | `src/components/ErrorDisplay.tsx` |
| `useAuthStore` | `src/stores/auth-store.ts` |
| `useTranslation` | `react-i18next` |

---

## FRs

**FR-015 — Consolidated Report (Multi-Level)**
- Reviewers see a consolidated report of all filing units within their scope.
- At org-unit level **1000處 and above** (1000, 0800, 0500, 0000): report displays **three column groups in parallel**:
  1. **部門營運預算** — from budget uploads (operational accounts)
  2. **人力預算** — from HR personnel imports (personnel-category accounts)
  3. **公攤費用** — from shared-cost imports (shared_cost-category accounts)
- Below 1000-level: `personnel_budget` and `shared_cost` columns are null → display as "—".
- Three "last updated" timestamps shown in table header or metadata area: `budget_last_updated_at`, `personnel_last_updated_at`, `shared_cost_last_updated_at`.
- Any of the three sources updating triggers immediate report update (backend handles; frontend re-fetches on manual refresh).

**FR-016 — Budget vs. Actuals Comparison**
- Each row includes `actual` (current year actuals from actuals import), `operational_budget` (from upload), and computed `delta_amount` (budget - actual) and `delta_pct` (percentage, 1 decimal).
- **`delta_pct` display rule:** when `actual === 0` (or actual is null/zero), display the string "N/A" — backend sends the literal string "N/A" for these rows; frontend renders it directly without further formatting.
- **`budget_status: "not_uploaded"` display rule:** display `t('report.status.not_uploaded')` — "未上傳". This means the filing unit has not uploaded its budget Excel for this cycle.
- `delta_amount` and amounts: monetary values arrive as strings (Decimal serialized as string per architecture CR-036). Format via `formatAmount()` from `src/lib/format-currency.ts`.

**FR-017 — Report Export**
- Supported formats: `xlsx` and `csv` only (not PDF — confirmed in build plan ambiguity #4).
- Export trigger: `POST /cycles/{cycle_id}/reports/exports?format=xlsx|csv`.
- Response can be:
  - **Sync** (201): `{ mode: "sync", file_url: string, expires_at: string }` — use `downloadBlob(file_url, filename)` immediately.
  - **Async** (202): `{ mode: "async", job_id: string }` — use `pollAndDownload(job_id, ...)` to poll `GET /exports/{job_id}` until `status: "succeeded"` then `GET /exports/{job_id}/file`.
- Export failure: `REPORT_002` (410) — show error message with retry button.
- Large export (>1000 units): backend uses async mode automatically; frontend must handle both modes transparently.

---

## Exports

- `ConsolidatedReportPage` — page component.
- `useConsolidatedReport` — wraps `getConsolidatedReport()` query.

---

## API Calls

| # | Method | Endpoint | Request | Response |
|---|--------|----------|---------|----------|
| 1 | GET | `/cycles/{cycle_id}/reports/consolidated` | — | `ConsolidatedReport` |
| 2 | POST | `/cycles/{cycle_id}/reports/exports` | query: `?format=xlsx\|csv` | 201 `{ mode: "sync", file_url, expires_at }` or 202 `{ mode: "async", job_id }` |
| 3 | GET | `/exports/{job_id}` | — | `{ status: "queued" | "running" | "succeeded" | "failed", result?: { file_url }, error_message?: string }` |
| 4 | GET | `/exports/{job_id}/file` | — | binary file (Content-Disposition: attachment) |

**`ConsolidatedReport` shape:**
```typescript
{
  cycle_id: string;
  rows: ConsolidatedReportRow[];
  reporting_currency: string;
  budget_last_updated_at: string | null;
  personnel_last_updated_at: string | null;
  shared_cost_last_updated_at: string | null;
}

interface ConsolidatedReportRow {
  org_unit_id: string;
  org_unit_name: string;
  account_code: string;
  account_name: string;
  actual: string | null;              // Decimal as string
  operational_budget: string | null;  // Decimal as string; null if not uploaded
  personnel_budget: string | null;    // Decimal as string; null below 1000-level
  shared_cost: string | null;         // Decimal as string; null below 1000-level
  delta_amount: string | null;        // Decimal as string; null if no budget
  delta_pct: string;                  // "N/A" when actual is 0; percentage string otherwise
  budget_status: 'uploaded' | 'not_uploaded' | 'resubmit_requested';
}
```

---

## UI States

| State | UI |
|-------|----|
| **Loading** | Full-page skeleton: metadata header skeleton + table with 5 skeleton rows |
| **Error** | `<ErrorDisplay error={err} />` with "重新載入" button |
| **Empty** | `REPORT_001` (404) case: "此週期尚無彙整資料" message |
| **Populated** | Three-column-group TanStack Table + export controls + metadata header |
| **Export loading** | Export button shows spinner; button disabled during export |
| **Export async polling** | Progress indicator showing "正在產生報表..."; polls `GET /exports/{job_id}` |
| **Export failed** | `REPORT_002` inline error with "重試" button |

---

## Table Layout (Three-Column Groups)

The report table uses TanStack Table with column grouping. Structure:

```
| 單位 | 會科 | ← 部門營運預算 → | ← 人力預算 → | ← 公攤費用 → |
|      |      | 實績 | 預算 | 增減 | 增減% | 人力預算 | 公攤費用 |
```

Column group 1 — **部門營運預算**:
- `actual` — formatted via `formatAmount()`, or "—" if null
- `operational_budget` — formatted via `formatAmount()`, or "未上傳" (from `budget_status`) if null
- `delta_amount` — formatted via `formatAmount()`, or "—" if null
- `delta_pct` — display raw string from API (may be "N/A" or "12.5%")

Column group 2 — **人力預算** (1000處+ only):
- `personnel_budget` — formatted via `formatAmount()`, or "—" if null

Column group 3 — **公攤費用** (1000處+ only):
- `shared_cost` — formatted via `formatAmount()`, or "—" if null

Rows below 1000-level have `personnel_budget: null` and `shared_cost: null` → cells display "—".

---

## User Interactions

1. **Cycle selector** — same as Dashboard: auto-select latest Open (or most recent) cycle from `GET /cycles`. Dropdown to switch.
2. **Export XLSX** — "匯出 Excel" button. Calls `POST /cycles/{id}/reports/exports?format=xlsx`. Handles sync and async response modes.
3. **Export CSV** — "匯出 CSV" button. Same flow with `?format=csv`.
4. **Manual refresh** — "重新整理" button calls `refetch()` on the report query.
5. **Column sorting** — TanStack Table `enableSorting: true` for numeric columns (actual, operational_budget, delta_amount). Sorting is client-side (report is fully loaded in one request).
6. **Metadata display** — show `reporting_currency` and three last-updated timestamps in a header info bar above the table. Format timestamps as localized date strings.

---

## Side-Effects

- `useConsolidatedReport` wraps `getConsolidatedReport()` with `staleTime: 60_000` (1 minute) — data does not auto-refresh; user triggers manually.
- Export flow (async mode): `pollAndDownload` from `src/lib/download.ts` handles the polling loop internally. The component only needs to call `pollAndDownload(jobId, pollUrl, fileUrl)` and await resolution.
- Export flow (sync mode): call `downloadBlob(file_url, filename)` directly.
- After successful export: no cache invalidation needed (export does not mutate state).

---

## Verbatim Display Rules

| Value | Display |
|-------|---------|
| `delta_pct` when actual is 0 | `"N/A"` (string from API, render as-is) |
| `budget_status === "not_uploaded"` | `t('report.status.not_uploaded')` → "未上傳" |
| `personnel_budget === null` | `"—"` |
| `shared_cost === null` | `"—"` |
| `actual === null` | `"—"` |
| All monetary amounts | `formatAmount()` from `src/lib/format-currency.ts` — never `parseFloat()` for display |
| Currency format | `Intl.NumberFormat('zh-TW', { style: 'decimal', minimumFractionDigits: 2 })` |

---

## Gotchas

- Route guard: `<RouteGuard roles={["FinanceAdmin", "UplineReviewer", "CompanyReviewer"]}>`. All three can access reports.
- **FCR-012 is fully applicable here** — the three-column layout must correctly show `personnel_budget` and `shared_cost` columns. Null values display "—". The `delta_pct` column renders the string value directly. The `budget_status` field "not_uploaded" is translated to the i18n key `report.status.not_uploaded`.
- **FCR-014 is fully applicable here** — use `formatAmount()` from `src/lib/format-currency.ts` for all monetary display. Never use raw `Number()` or `parseFloat()` for display purposes.
- The export endpoint path is `POST /cycles/{cycle_id}/reports/exports` (plural "exports") — note from build plan, not from the architecture doc. Use this path.
- `pollAndDownload` from `src/lib/download.ts` must be called with `refetchInterval`-style polling. The implementation in `download.ts` handles this; the page just awaits the promise.
- The report can be large (hundreds of rows × many account codes). TanStack Table virtualization may be needed if > 500 rendered rows — note this as a performance consideration but do not implement virtual scrolling until a real data size is confirmed.
- `ConsolidatedReportPage` may approach 400 lines due to TanStack Table column config. If so, extract column definitions to `src/features/consolidated-report/reportColumns.ts`.
- CompanyReviewer (0000) accesses this page directly from the report link banner in Dashboard.

---

## Tests

1. **Renders three-column-group table with correct column headers** — mock `getConsolidatedReport` returning sample rows; assert column headers for "部門營運預算", "人力預算", "公攤費用" groups present.
2. **Null personnel_budget and shared_cost display as "—"** — mock rows with `personnel_budget: null, shared_cost: null`; assert those cells render "—" not empty or "null".
3. **delta_pct "N/A" renders correctly** — mock row with `delta_pct: "N/A"`; assert cell shows "N/A" string.
4. **budget_status "not_uploaded" shows "未上傳"** — mock row with `budget_status: "not_uploaded", operational_budget: null`; assert cell shows `t('report.status.not_uploaded')`.
5. **Export async flow: pollAndDownload called on 202 response** — spy on `pollAndDownload`; click "匯出 Excel"; mock returns 202 `{ mode: "async", job_id: "job-1" }`; assert `pollAndDownload` called with `"job-1"`.
6. **Export sync flow: downloadBlob called on 201 response** — spy on `downloadBlob`; click "匯出 CSV"; mock returns 201 `{ mode: "sync", file_url: "/exports/file-1.csv" }`; assert `downloadBlob` called with that URL.

---

## Consistency Constraints

- **FCR-001:** This module uses the shared `apiClient` from `src/api/client.ts` for all HTTP requests. It does NOT create its own axios instance or use raw `fetch()`. The CSRF token is read from `document.cookie` and set as `X-CSRF-Token` by the request interceptor.
- **FCR-002:** This page component is wrapped in `<RouteGuard roles={["FinanceAdmin", "UplineReviewer", "CompanyReviewer"]}>`. The route appears in the sidebar for all three roles.
- **FCR-004:** All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
- **FCR-005:** API errors caught by mutation `onError` callbacks are passed to `<ErrorDisplay error={err} />`. The component is NOT duplicated or reimplemented locally.
- **FCR-007:** Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
- **FCR-008:** File downloads in this component use `downloadBlob()` or `pollAndDownload()` from `src/lib/download.ts`. No manual `window.open()`, `a.click()`, or direct blob handling.
- **FCR-009:** The API function in `reports.ts` defines a zod schema for the response and calls `.parse()` or `.safeParse()` on `response.data` before returning.
- **FCR-010:** This page checks `isLoading`, `isError`, and `data?.rows.length === 0` from its query hook and renders appropriate UI for each state.
- **FCR-012:** The report table renders `personnel_budget` and `shared_cost` columns. Null values display "—". The `delta_pct` column renders the string value directly (backend sends "N/A" for zero-actual rows). The `budget_status` field "not_uploaded" is translated to the i18n key `report.status.not_uploaded`.
- **FCR-013:** Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
- **FCR-014:** Monetary amounts are formatted via `formatAmount()` from `src/lib/format-currency.ts`. No raw `Number()` or `parseFloat()` for display purposes.
