# Spec: Shared Cost Import Page (`/shared-cost-import`)

**Sub-batch:** 8b (moderate)

---

## Module Metadata

| Key | Value |
|-----|-------|
| Module path | `frontend/src/pages/shared-cost-import/SharedCostImportPage.tsx` |
| Test path | `frontend/tests/unit/pages/shared-cost-import/SharedCostImportPage.test.tsx` |
| API module | `frontend/src/api/shared-costs.ts` |
| Hook | `frontend/src/features/shared-cost-import/useSharedCostImport.ts` |
| FRs | FR-027, FR-028, FR-029 |
| Exports | `SharedCostImportPage`, `useSharedCostImport` |

---

## Imports

| Symbol | Source module |
|--------|--------------|
| `apiClient` | `src/api/client.ts` |
| `importSharedCosts`, `listSharedCostVersions`, `getSharedCostImport` | `src/api/shared-costs.ts` |
| `ErrorDisplay` | `src/components/ErrorDisplay.tsx` |
| `DataTable` | `src/components/DataTable.tsx` |
| `useAuthStore` | `src/stores/auth-store.ts` |
| `useTranslation` | `react-i18next` |

---

## FRs

**FR-027 — Import Shared Costs**
- Upload: CSV or XLSX. Required columns: `dept_id` (org unit code), `account_code`, `amount`.
- Validation rules:
  - `dept_id` must exist in org tree → error `SHARED_001`
  - `account_code` must exist in account master (any category; NOT restricted to shared_cost-only per FR-027 text, but `SHARED_002` fires if category is wrong) → error `SHARED_002`
  - `amount` must be a positive number → error `SHARED_003`
- Integral commit semantics: if any row fails, entire batch rejected. Error `SHARED_004` (400) carries `details[]`.
- Roles: FinanceAdmin.

**FR-028 — Shared Cost Version Management**
- Same cycle may be imported multiple times; each import creates a new version snapshot.
- Version records: timestamp, uploader user, `affected_org_units_summary` (list of org unit codes changed), implied amount delta summary (backend computes; surfaced in `affected_org_units_summary` if extended).
- Historical versions read-only.
- Upload events recorded in audit log.

**FR-029 — Shared Cost Notification (P1)**
- After successful import: backend notifies affected department managers (departments where shared cost amounts changed).
- This is a P1 requirement — notification is triggered by backend on successful import; frontend only needs to show success state.

---

## Exports

- `SharedCostImportPage` — page component.
- `useSharedCostImport` — wraps `importSharedCosts()` mutation and `listSharedCostVersions()` query.

---

## API Calls

| # | Method | Endpoint | Request | Response |
|---|--------|----------|---------|----------|
| 1 | POST | `/cycles/{cycle_id}/shared-cost-imports` | multipart `file` (CSV/XLSX) | 201 `SharedCostUploadRead` |
| 2 | GET | `/cycles/{cycle_id}/shared-cost-imports` | — | `SharedCostUploadRead[]` |
| 3 | GET | `/shared-cost-imports/{upload_id}` | — | `SharedCostUploadRead` |

**`SharedCostUploadRead` shape:**
```typescript
{
  id: string;
  cycle_id: string;
  uploader_user_id: string;
  uploaded_at: string;             // ISO-8601 UTC
  filename: string;
  version: number;
  affected_org_units_summary: string[];  // list of org unit codes
}
```

---

## UI States

| State | UI |
|-------|----|
| **Loading** | Skeleton for version history table |
| **Error** | `<ErrorDisplay error={err} />`. `SHARED_004` shows collapsible row-level error table |
| **No Open Cycle** | "目前無開放中的預算週期" message; upload disabled |
| **Empty** | "尚未匯入任何公攤費用" message with file upload zone |
| **Populated** | File upload zone + version history table |

---

## User Interactions

1. **File upload** — Mantine `FileInput` accepting `.csv` and `.xlsx`. On select: call `importSharedCosts(cycleId, file)`. Show loading indicator.
2. **Version history table** — columns: version, uploaded_at, filename, `affected_org_units_summary` (comma-joined list).
3. **Version detail** — optional: click row to load `getSharedCostImport(id)` in a side panel.
4. **Manual refresh** — icon button calls `refetch()`.
5. **Cycle resolution** — same as PersonnelImportPage: `GET /cycles?status=Open` on mount.

---

## Side-Effects

- `importSharedCosts` mutation: on success, invalidates `['sharedCostVersions', cycleId]`.
- No polling; one-shot query per mount + manual refresh.
- On CYCLE_004 (closed cycle), mutation error caught by `onError` → `ErrorDisplay`.

---

## Verbatim Error Codes

| Code | Meaning |
|------|---------|
| `SHARED_001` | dept_id not in org tree |
| `SHARED_002` | account_code not shared_cost category |
| `SHARED_003` | amount must be positive |
| `SHARED_004` | batch validation failed (carries row-level `details[]`) |
| `CYCLE_004` | cycle is closed |

---

## Gotchas

- Route guard: `<RouteGuard roles={["FinanceAdmin"]}>`.
- Nearly identical structure to PersonnelImportPage; do NOT share the same hook or component — feature isolation is required per build plan.
- `SHARED_004` collect-then-report errors must be displayed as a table via `ErrorDisplay` (same as `PERS_004` handling).
- `affected_org_units_summary` may contain many entries; display as a truncated list with "展開" option if >5 entries.
- FR-029 is P1; the backend handles notifications. Frontend shows success toast; no additional notification-trigger logic in the UI.

---

## Tests

1. **Renders file upload zone and empty version history** — mock `listSharedCostVersions` returns `[]`; assert empty state message and file input present.
2. **Successful import shows new version row** — mock `importSharedCosts` returning 201; assert version table refetches and shows new entry.
3. **SHARED_004 row-level errors via ErrorDisplay** — mock returning 400 `{ error: { code: 'SHARED_004', details: [{row:5, column:'account_code', reason:'not shared_cost category'}] } }`; assert `ErrorDisplay` shows row table.
4. **No-cycle empty state disables upload** — mock cycle list empty; assert "無開放週期" and `FileInput` is disabled.
5. **Loading state during upload** — mock delayed response; assert spinner/loader present while mutation pending.

---

## Consistency Constraints

- **FCR-001:** This module uses the shared `apiClient` from `src/api/client.ts` for all HTTP requests. It does NOT create its own axios instance or use raw `fetch()`. The CSRF token is read from `document.cookie` and set as `X-CSRF-Token` by the request interceptor.
- **FCR-002:** This page component is wrapped in `<RouteGuard roles={["FinanceAdmin"]}>`. The route appears in the sidebar only for FinanceAdmin.
- **FCR-004:** All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
- **FCR-005:** API errors caught by mutation `onError` callbacks are passed to `<ErrorDisplay error={err} />`. The component is NOT duplicated or reimplemented locally.
- **FCR-007:** Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
- **FCR-009:** The API function in `shared-costs.ts` defines a zod schema for the response and calls `.parse()` or `.safeParse()` on `response.data` before returning.
- **FCR-010:** This page checks `isLoading`, `isError`, and `data?.length === 0` from its query hook and renders appropriate UI for each state.
- **FCR-013:** Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
