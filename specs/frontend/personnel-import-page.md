# Spec: HR Personnel Import Page (`/personnel-import`)

**Sub-batch:** 8b (moderate)

---

## Module Metadata

| Key | Value |
|-----|-------|
| Module path | `frontend/src/pages/personnel-import/PersonnelImportPage.tsx` |
| Test path | `frontend/tests/unit/pages/personnel-import/PersonnelImportPage.test.tsx` |
| API module | `frontend/src/api/personnel.ts` |
| Hook | `frontend/src/features/personnel-import/usePersonnelImport.ts` |
| FRs | FR-024, FR-025, FR-026 |
| Exports | `PersonnelImportPage`, `usePersonnelImport` |

---

## Imports

| Symbol | Source module |
|--------|--------------|
| `apiClient` | `src/api/client.ts` |
| `importPersonnel`, `listPersonnelVersions`, `getPersonnelImport` | `src/api/personnel.ts` |
| `ErrorDisplay` | `src/components/ErrorDisplay.tsx` |
| `DataTable` | `src/components/DataTable.tsx` |
| `useAuthStore` | `src/stores/auth-store.ts` |
| `useTranslation` | `react-i18next` |

---

## FRs

**FR-024 — Import Personnel Budget**
- Upload: CSV or XLSX file. Required columns: `dept_id` (org unit code), `account_code`, `amount`.
- Validation rules:
  - `dept_id` must exist in org tree → error `PERS_001`
  - `account_code` must exist in account master AND be `category = 'personnel'` → error `PERS_002`
  - `amount` must be a positive number → error `PERS_003`
- Integral commit semantics: if any row fails, entire batch is rejected. Error `PERS_004` (400) carries `details[]` array.
- Roles: HRAdmin.

**FR-025 — Personnel Version Management**
- Same cycle may be imported multiple times; each import creates a new version snapshot.
- Each version records: timestamp, uploader user, `affected_org_units_summary` (list of org unit codes that changed).
- Historical versions are read-only.
- Upload events recorded in audit log.
- Each new import overwrites the previous for affected org units (latest version is the effective version).

**FR-026 — Personnel Import Notification**
- After successful import: backend sends email notification to FinanceAdmin(s).
- Consolidated report automatically reflects new data.
- From the frontend perspective: successful mutation is sufficient; no additional notification trigger needed.

---

## Exports

- `PersonnelImportPage` — page component.
- `usePersonnelImport` — wraps `importPersonnel()` mutation and `listPersonnelVersions()` query.

---

## API Calls

| # | Method | Endpoint | Request | Response |
|---|--------|----------|---------|----------|
| 1 | POST | `/cycles/{cycle_id}/personnel-imports` | multipart `file` (CSV/XLSX) | 201 `PersonnelImportRead` |
| 2 | GET | `/cycles/{cycle_id}/personnel-imports` | — | `PersonnelImportRead[]` |
| 3 | GET | `/personnel-imports/{id}` | — | `PersonnelImportRead` |

**`PersonnelImportRead` shape:**
```typescript
{
  id: string;
  cycle_id: string;
  uploader_user_id: string;
  uploaded_at: string;      // ISO-8601 UTC
  filename: string;
  file_hash: string;
  version: number;
  affected_org_units_summary: string[];  // list of org unit codes
}
```

---

## UI States

| State | UI |
|-------|----|
| **Loading** | Skeleton for version history table |
| **Error** | `<ErrorDisplay error={err} />`. `PERS_004` shows collapsible row-level error table (row, column, reason). |
| **No Open Cycle** | "目前無開放中的預算週期" message; upload disabled |
| **Empty** | "尚未匯入任何人力預算" message with file upload zone |
| **Populated** | File upload zone (always visible) + version history table below |

---

## User Interactions

1. **File upload** — Mantine `FileInput` accepting `.csv` and `.xlsx`. On select: call `importPersonnel(cycleId, file)` via `FormData`. Show loading spinner during upload.
2. **Version history table** — columns: version number, uploaded_at, filename, file_hash (truncated), `affected_org_units_summary` (comma-joined or expandable chip list).
3. **View import detail** — clicking a version row could show `getPersonnelImport(id)` result in a side panel or modal (optional detail view).
4. **Manual refresh** — icon button calls `refetch()` on version list.
5. **Cycle selector** — page resolves current Open cycle on mount via `GET /cycles?status=Open`. No cycle picker needed (HRAdmin uploads to the current Open cycle only).

---

## Side-Effects

- `importPersonnel` mutation: on success, invalidates `['personnelVersions', cycleId]`.
- `listPersonnelVersions`: no polling; read once per mount and on manual refresh.
- `cycle_id` is resolved from `GET /cycles?status=Open` (same pattern as UploadPage); if no Open cycle, show disabled state.

---

## Verbatim Error Codes (to be displayed via ErrorDisplay)

| Code | Meaning |
|------|---------|
| `PERS_001` | dept_id not in org tree |
| `PERS_002` | account_code not personnel category |
| `PERS_003` | amount must be positive |
| `PERS_004` | batch validation failed (carries row-level `details[]`) |
| `CYCLE_004` | cycle is closed; no new imports accepted |

---

## Gotchas

- Route guard: `<RouteGuard roles={["HRAdmin"]}>`.
- The accepted file types are `.csv` AND `.xlsx` (not just xlsx like budget uploads). The `FileInput` `accept` prop should include both MIME types.
- `PERS_004` is a collect-then-report error; `details[]` contains objects with `row`, `column`, `reason` — `ErrorDisplay` must render these as a table.
- `affected_org_units_summary` is a list of org unit codes (strings) — display as a compact list, not individual badges (could be many).
- File hash is shown truncated (first 8 chars) in the version table for space reasons.
- HRAdmin has no Dashboard or Reports nav; ensure the sidebar reflects this (handled by `ShellLayout` + `useAuthStore`).

---

## Tests

1. **Renders file upload zone and empty version history** — mock `listPersonnelVersions` returns `[]`; assert empty state and file input present.
2. **Successful import shows new version in history** — mock `importPersonnel` returning 201; assert version history refetches and new row appears.
3. **PERS_004 row-level errors rendered via ErrorDisplay** — mock `importPersonnel` returning 400 `{ error: { code: 'PERS_004', details: [{row:3, column:'dept_id', reason:'not in org tree'}] } }`; assert `ErrorDisplay` with row table visible.
4. **Loading state shown during upload** — mock `importPersonnel` with delayed response; assert loading indicator present while pending.
5. **No-cycle empty state** — mock `listCycles?status=Open` returning `[]`; assert "無開放週期" message and disabled upload zone.

---

## Consistency Constraints

- **FCR-001:** This module uses the shared `apiClient` from `src/api/client.ts` for all HTTP requests. It does NOT create its own axios instance or use raw `fetch()`. The CSRF token is read from `document.cookie` and set as `X-CSRF-Token` by the request interceptor.
- **FCR-002:** This page component is wrapped in `<RouteGuard roles={["HRAdmin"]}>`. The route appears in the sidebar only for HRAdmin.
- **FCR-004:** All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
- **FCR-005:** API errors caught by mutation `onError` callbacks are passed to `<ErrorDisplay error={err} />`. The component is NOT duplicated or reimplemented locally.
- **FCR-007:** Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
- **FCR-009:** The API function in `personnel.ts` defines a zod schema for the response and calls `.parse()` or `.safeParse()` on `response.data` before returning.
- **FCR-010:** This page checks `isLoading`, `isError`, and `data?.length === 0` from its query hook and renders appropriate UI for each state.
- **FCR-013:** Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
