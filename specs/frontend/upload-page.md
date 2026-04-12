# Spec: Filing-Unit Upload Page (`/upload`)

**Sub-batch:** 8b (moderate)

---

## Module Metadata

| Key | Value |
|-----|-------|
| Module path | `frontend/src/pages/upload/UploadPage.tsx` |
| Test path | `frontend/tests/unit/pages/upload/UploadPage.test.tsx` |
| API modules | `frontend/src/api/budget-uploads.ts`, `frontend/src/api/templates.ts` |
| Hook | `frontend/src/features/budget-uploads/useBudgetUpload.ts` |
| FRs | FR-010, FR-011, FR-012 |
| Exports | `UploadPage`, `useBudgetUpload` |

---

## Imports

| Symbol | Source module |
|--------|--------------|
| `apiClient` | `src/api/client.ts` |
| `uploadBudget`, `listUploadVersions`, `getUpload` | `src/api/budget-uploads.ts` |
| `downloadTemplate` | `src/api/templates.ts` |
| `useAuthStore` | `src/stores/auth-store.ts` |
| `ErrorDisplay` | `src/components/ErrorDisplay.tsx` |
| `StatusBadge` | `src/components/StatusBadge.tsx` |
| `downloadBlob` | `src/lib/download.ts` |
| `DataTable` | `src/components/DataTable.tsx` |
| `useTranslation` | `react-i18next` |

---

## FRs

**FR-010 — Template Download**
- FilingUnitManager logs in and downloads the template for their own org unit.
- Endpoint: `GET /cycles/{cycle_id}/templates/{org_unit_id}/download` — returns binary `.xlsx`.
- Uses `downloadBlob` helper to trigger browser file save.
- Error `TPL_002` (404) if template not yet generated for unit — show specific message.
- The `org_unit_id` comes from the authenticated user's profile (`useAuthStore().user.org_unit_id`).

**FR-011 — Upload Budget Excel**
- File type: `.xlsx` only; size limit: 10 MB; row limit: 5,000 rows.
- Validation errors returned as row-level details: row number + column + reason.
- Error codes:
  - `UPLOAD_001` (413): file size > 10 MB
  - `UPLOAD_002` (400): row count > 5,000
  - `UPLOAD_003` (400, row-level): dept code mismatch
  - `UPLOAD_004` (400, row-level): required cell empty
  - `UPLOAD_005` (400, row-level): amount format invalid
  - `UPLOAD_006` (400, row-level): negative amount
  - `UPLOAD_007` (400): batch validation failed — carries `details[]` array
- Integral commit: zero rows persisted on any validation failure.
- On success: returns `BudgetUploadRead` with new version number.
- Roles: FilingUnitManager.

**FR-012 — Version History**
- Each successful upload auto-creates a new version (version number, uploader_id, timestamp, file_size_bytes).
- Version list displayed chronologically; latest version marked as "有效版本".
- Historical versions are read-only; version list persists until 5 years after cycle close.
- Endpoint: `GET /cycles/{cycle_id}/uploads/{org_unit_id}` returns `BudgetUploadRead[]`.

---

## Exports

- `UploadPage` — page component.
- `useBudgetUpload` — wraps `uploadBudget()` mutation and `listUploadVersions()` query.

---

## API Calls

| # | Method | Endpoint | Request | Response |
|---|--------|----------|---------|----------|
| 1 | GET | `/cycles/{cycle_id}/templates/{org_unit_id}/download` | — | binary `.xlsx` (Content-Disposition: attachment) |
| 2 | POST | `/cycles/{cycle_id}/uploads/{org_unit_id}` | multipart `file` field (.xlsx, ≤10 MB) | 201 `BudgetUploadRead` |
| 3 | GET | `/cycles/{cycle_id}/uploads/{org_unit_id}` | — | `BudgetUploadRead[]` |

**`BudgetUploadRead` shape:**
```typescript
{
  id: string;
  cycle_id: string;
  org_unit_id: string;
  version: number;
  uploader_id: string;
  row_count: number;
  file_size_bytes: number;
  status: 'Pending' | 'Valid' | 'Invalid';
  uploaded_at: string;  // ISO-8601 UTC
}
```

---

## UI States

| State | UI |
|-------|----|
| **Loading** | Mantine Skeleton covering the version history table and current status area |
| **Error** | `<ErrorDisplay error={err} />`. Batch validation errors (UPLOAD_007) show row-level `details[]` in collapsible table |
| **Empty / No cycle open** | "目前無開放中的預算週期" message. No upload controls rendered. |
| **Ready to upload** | "下載樣板" button + `StatusBadge` showing current status + file dropzone + version history table |
| **Upload success** | Success notification; version history table refreshes; status badge updates |

---

## User Interactions

1. **Download template** — "下載樣板" button. Calls `downloadTemplate(cycleId, orgUnitId)` which returns blob URL. Delegates to `downloadBlob()`. On `TPL_002`: show `t('upload.error.template_not_found')`.
2. **File upload** — Mantine `FileInput` (or dropzone) accepting `.xlsx` files. Client-side pre-check: file size ≤ 10 MB (show `t('upload.error.file_too_large')` immediately without API call). On select: call `uploadBudget(cycleId, orgUnitId, file)` via `FormData` multipart. Show progress indicator during upload.
3. **View version history** — `DataTable` below the upload zone showing all versions (newest first): version number, upload timestamp, row_count, file_size_bytes, status badge, uploader display.
4. **Status badge** — `<StatusBadge status={latestUpload?.status ?? 'not_uploaded'} />`. Maps:
   - No uploads → `'not_uploaded'` (grey)
   - `Valid` → `'uploaded'` (green)
   - `Pending` → intermediate (amber) during processing
   - `Invalid` → error (red)
5. **Manual refresh** — "重新整理" icon button; calls `refetch()` on the version list query.

---

## Side-Effects

- `uploadBudget` mutation: on success, invalidates `['uploadVersions', cycleId, orgUnitId]` query.
- `listUploadVersions`: no polling (FilingUnitManager does not need live updates beyond manual refresh).
- The `cycle_id` for the current open cycle must be determined by the page. Strategy: the page fetches `GET /cycles?status=Open` on mount (via a lightweight query) and uses the first result. If no Open cycle exists, renders the no-cycle empty state.
- `org_unit_id` sourced from `useAuthStore().user.org_unit_id` — never accept from URL params (security: FilingUnitManager must only upload to their own org unit).

---

## Verbatim Status Strings

- Status `not_uploaded` → `t('upload.status.not_uploaded')` — "未上傳"
- Status `uploaded` (Valid) → `t('upload.status.uploaded')` — "已上傳"
- Status `resubmit` → `t('upload.status.resubmit')` — "已通知重傳"

---

## Gotchas

- Route guard: `<RouteGuard roles={["FilingUnitManager"]}>`.
- Client-side 10 MB check before calling API prevents wasted network round-trip for obvious oversize files. Error `UPLOAD_001` from backend also handled via `ErrorDisplay`.
- `UPLOAD_007` response carries `details[]` with row-level errors — `ErrorDisplay` must render these as a table (this is the collect-then-report pattern).
- The page must never show another org unit's data; `org_unit_id` always comes from `useAuthStore`, not URL.
- Do not implement historical version download until the backend endpoint is confirmed live (per build plan ambiguity #2 — deferred).
- File size is displayed in human-readable format (KB/MB) in the version history table — format utility from `src/lib/format-currency.ts` or a separate `format-bytes.ts` helper.

---

## Tests

1. **Shows "下載樣板" button and no version history on empty** — mock `listUploadVersions` returning `[]`; assert empty state for version table; "下載樣板" button present.
2. **Download template triggers downloadBlob** — spy on `downloadBlob`; click button; assert called with correct URL pattern.
3. **File upload — client-side size validation** — attach a mock file >10 MB; assert error message shown without API call.
4. **File upload — UPLOAD_007 row-level errors rendered** — mock `uploadBudget` returning 400 `{ error: { code: 'UPLOAD_007', details: [{row:2, column:'amount', reason:'negative'}] } }`; assert `ErrorDisplay` shows row-level table.
5. **Successful upload refreshes version list** — mock `uploadBudget` returning 201; assert `StatusBadge` updates and version history table shows new row.

---

## Consistency Constraints

- **FCR-001:** This module uses the shared `apiClient` from `src/api/client.ts` for all HTTP requests. It does NOT create its own axios instance or use raw `fetch()`. The CSRF token is read from `document.cookie` and set as `X-CSRF-Token` by the request interceptor.
- **FCR-002:** This page component is wrapped in `<RouteGuard roles={["FilingUnitManager"]}>`. The route appears in the sidebar only for FilingUnitManager.
- **FCR-003:** This component references status colors via the theme object or via `StatusBadge`. No hardcoded hex color strings for status indicators.
- **FCR-004:** All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
- **FCR-005:** API errors caught by mutation `onError` callbacks are passed to `<ErrorDisplay error={err} />`. The component is NOT duplicated or reimplemented locally.
- **FCR-007:** Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
- **FCR-008:** File downloads in this component use `downloadBlob()` or `pollAndDownload()` from `src/lib/download.ts`. No manual `window.open()`, `a.click()`, or direct blob handling.
- **FCR-009:** The API function in `budget-uploads.ts` and `templates.ts` defines a zod schema for the response and calls `.parse()` or `.safeParse()` on `response.data` before returning.
- **FCR-010:** This page checks `isLoading`, `isError`, and `data?.length === 0` from its query hook and renders appropriate UI for each state.
- **FCR-013:** Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
