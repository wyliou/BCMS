# Spec: Cycle Admin Page (`/admin/cycles`)

**Sub-batch:** 8b (moderate)

---

## Module Metadata

| Key | Value |
|-----|-------|
| Module path | `frontend/src/pages/admin/CycleAdminPage.tsx` |
| Test path | `frontend/tests/unit/pages/admin/CycleAdminPage.test.tsx` |
| API module | `frontend/src/api/cycles.ts` |
| Hook | `frontend/src/features/cycles/useCycles.ts` |
| FRs | FR-001, FR-003, FR-005, FR-006 |
| Exports | `CycleAdminPage`, `useCycles` |

---

## Imports

| Symbol | Source module |
|--------|--------------|
| `apiClient` | `src/api/client.ts` |
| `listCycles`, `getCycle`, `createCycle`, `openCycle`, `closeCycle`, `reopenCycle`, `setReminders`, `getFilingUnits` | `src/api/cycles.ts` |
| `regenerateTemplate` | `src/api/templates.ts` |
| `ErrorDisplay` | `src/components/ErrorDisplay.tsx` |
| `DataTable` | `src/components/DataTable.tsx` |
| `useAuthStore` | `src/stores/auth-store.ts` |
| `useTranslation` | `react-i18next` |

---

## FRs

**FR-001 — Create Budget Cycle**
- Inputs: `fiscal_year` (int), `deadline` (date), `reporting_currency` (string).
- Constraint: one active cycle per fiscal year.
- Error: `CYCLE_001` (409) if year already has an active cycle.
- Roles: FinanceAdmin, SystemAdmin.

**FR-003 — Open Cycle**
- Transition: Draft → Open only; cannot re-open an already Open or Closed cycle.
- On open: system auto-generates templates and sends email notifications to all filing-unit managers (excluding 0000 company).
- Response: `OpenCycleResponse { cycle, transition, generation_summary: { total, generated, errors, error_details[] }, dispatch_summary: { total_recipients, sent, errors } }`.
- Errors: `CYCLE_002` (409) filing unit missing manager; `CYCLE_003` (409) not in Draft state.
- Template generation failures are non-blocking (cycle stays Open); surfaced in `generation_summary.error_details[]` — UI shows per-unit errors with a "重試" button per failed unit.
- Notification bounce failures: non-blocking; shown in `dispatch_summary.errors`.
- Role: FinanceAdmin.

**FR-005 — Deadline Reminders**
- Set reminder schedule: `{ days_before: int[] }` (e.g. `[7, 3, 1]`).
- Backend cron fires daily at 09:00 server time; already-uploaded units excluded automatically.
- Endpoint: `PATCH /cycles/{cycle_id}/reminders`.
- Role: FinanceAdmin.

**FR-006 — Close / Reopen Cycle**
- Close: Open → Closed (one-way). After close: no new uploads or imports accepted.
- On upload to closed cycle: backend returns `CYCLE_004` (409) "週期已關閉".
- Reopen: requires `reason` string; only within reopen window (backend enforces ≤ 7 days default); error `CYCLE_005` (409) if window expired.
- Reopen role: SystemAdmin only (FinanceAdmin can close, not reopen).

---

## Exports

- `CycleAdminPage` — default page component.
- `useCycles` — TanStack Query hook wrapping `listCycles()`, `createCycle()`, `openCycle()`, `closeCycle()`, `reopenCycle()`, `setReminders()`.

---

## API Calls

| # | Method | Endpoint | Request | Response |
|---|--------|----------|---------|----------|
| 1 | GET | `/cycles` | `?fiscal_year=` | `CycleRead[]` |
| 2 | POST | `/cycles` | `{ fiscal_year: int, deadline: date, reporting_currency: string }` | 201 `CycleRead` |
| 3 | GET | `/cycles/{cycle_id}` | — | `CycleRead` |
| 4 | GET | `/cycles/{cycle_id}/filing-units` | — | `FilingUnitInfoRead[] { org_unit_id, code, name, has_manager, excluded, warnings[] }` |
| 5 | POST | `/cycles/{cycle_id}/open` | — | `OpenCycleResponse { cycle, transition, generation_summary: { total, generated, errors, error_details[] }, dispatch_summary: { total_recipients, sent, errors } }` |
| 6 | POST | `/cycles/{cycle_id}/close` | — | `CycleRead` |
| 7 | POST | `/cycles/{cycle_id}/reopen` | `{ reason: string }` | `CycleRead` |
| 8 | PATCH | `/cycles/{cycle_id}/reminders` | `{ days_before: int[] }` | `ReminderScheduleRead[]` |
| 9 | POST | `/cycles/{cycle_id}/templates/{org_unit_id}/regenerate` | — | `TemplateGenerationResult { org_unit_id, status, error? }` |

**`CycleRead` shape:**
```typescript
{
  id: string;
  fiscal_year: number;
  deadline: string;          // ISO date
  reporting_currency: string;
  status: 'Draft' | 'Open' | 'Closed';
  opened_at: string | null;
  closed_at: string | null;
  reopened_at: string | null;
}
```

---

## UI States

| State | UI |
|-------|----|
| **Loading** | Mantine Skeleton for the cycle list table and detail panel |
| **Error** | `<ErrorDisplay error={err} />` — covers CYCLE_001, CYCLE_002, CYCLE_003, CYCLE_004, CYCLE_005 |
| **Empty** | "尚未建立任何預算週期" message with "建立週期" button |
| **Populated — Draft** | Cycle row with "開放週期" button; shows pre-open filing-unit check (filing-units loaded from `GET /filing-units`; units with `has_manager: false` shown with warning icon; units with `warnings[]` expandable). "開放週期" button disabled if any `has_manager: false` unexcluded units exist. |
| **Populated — Open** | Cycle row shows "已開放"; "關閉週期" button; reminder schedule form; generation summary errors with per-unit "重試" buttons |
| **Populated — Closed** | Cycle row shows "已關閉"; "重開週期" button (SystemAdmin only); no further action buttons for FinanceAdmin |

---

## User Interactions

1. **Create cycle** — form with `fiscal_year` number input, `deadline` date picker, `reporting_currency` text input. On submit: `POST /cycles`. On `CYCLE_001`: show `ErrorDisplay`.
2. **Pre-open check** — when cycle is Draft and user expands it, auto-fetch `GET /cycles/{id}/filing-units`. Display table of filing units with `has_manager` flag warnings. Confirm-to-open button disabled if any non-excluded unit lacks a manager.
3. **Open cycle** — "開放週期" button calls `POST /cycles/{id}/open`. Show loading state during request (may take seconds for template generation). On success: show `generation_summary` panel; any `error_details[]` displayed with per-row unit name + error.
4. **Retry template generation** — "重試" button per failed unit calls `POST /cycles/{id}/templates/{org_unit_id}/regenerate`.
5. **Set reminders** — multi-select or chip group for `days_before`; PATCH on change. Values must be positive integers.
6. **Close cycle** — "關閉週期" confirmation dialog → `POST /cycles/{id}/close`.
7. **Reopen cycle** — "重開週期" (SystemAdmin only); text area for `reason` required; `POST /cycles/{id}/reopen`. On `CYCLE_005`: show specific error message.

---

## Side-Effects

- `createCycle` mutation: on success, invalidates `['cycles']` query.
- `openCycle` mutation: on success, invalidates `['cycles', cycleId]`.
- `closeCycle` / `reopenCycle`: same — invalidate `['cycles', cycleId]`.
- `setReminders`: invalidates reminder schedule query.
- `regenerateTemplate`: invalidates nothing (backend streams result immediately); updates local state for that unit.

---

## Verbatim Status Strings

Map `cycle.status` to i18n keys:
- `'Draft'` → `t('cycle.status.draft')` — "草稿"
- `'Open'` → `t('cycle.status.open')` — "已開放"
- `'Closed'` → `t('cycle.status.closed')` — "已關閉"

Error display copy (from PRD §4.1):
- `CYCLE_004`: `t('cycle.error.closed')` — "週期已關閉"

---

## Gotchas

- Route guard: `<RouteGuard roles={["FinanceAdmin", "SystemAdmin"]}>`. Reopen action rendered only for `SystemAdmin`.
- The open-cycle operation is slow (template generation + email dispatch). Show a loading indicator and do not allow double-submit.
- `generation_summary.error_details[]` items identify the `org_unit_id`; the frontend must resolve to org unit name from the previously loaded filing-units list.
- `CYCLE_002` fires when the backend detects a unit without a manager during open — the frontend pre-open check should catch this, but the backend is the source of truth.
- `days_before` array must contain only positive integers (validate on client before PATCH).
- Cycle list may be empty on first visit — show appropriate empty state with CTA.

---

## Tests

1. **Renders cycle list** — mock `listCycles` returning 2 cycles (one Draft, one Closed); assert both rows appear with correct status badges and action buttons.
2. **Create cycle form validation** — submit form with empty `fiscal_year`; assert form validation error shown before API call. Then submit valid data; mock returns 201; assert cycle appears in list.
3. **Open cycle shows generation summary** — mock `openCycle` returning summary with 1 error in `generation_summary.error_details[]`; assert error row visible with "重試" button; click "重試"; assert `regenerateTemplate` called.
4. **Close cycle requires confirmation** — click "關閉週期"; assert confirmation dialog appears before mutation fires.
5. **ErrorDisplay shown on CYCLE_003** — mock `openCycle` returning 409 `CYCLE_003`; assert `<ErrorDisplay>` rendered with correct error code.

---

## Consistency Constraints

- **FCR-001:** This module uses the shared `apiClient` from `src/api/client.ts` for all HTTP requests. It does NOT create its own axios instance or use raw `fetch()`. The CSRF token is read from `document.cookie` and set as `X-CSRF-Token` by the request interceptor.
- **FCR-002:** This page component is wrapped in `<RouteGuard roles={["FinanceAdmin", "SystemAdmin"]}>`. The route appears in the sidebar only for those roles.
- **FCR-004:** All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
- **FCR-005:** API errors caught by mutation `onError` callbacks are passed to `<ErrorDisplay error={err} />`. The component is NOT duplicated or reimplemented locally.
- **FCR-007:** Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
- **FCR-009:** The API function in `cycles.ts` and `templates.ts` defines a zod schema for the response and calls `.parse()` or `.safeParse()` on `response.data` before returning.
- **FCR-010:** This page checks `isLoading`, `isError`, and `data?.length === 0` from its query hook and renders appropriate UI for each state.
- **FCR-013:** Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
