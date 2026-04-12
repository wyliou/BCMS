# Spec: Resubmit Modal (feature component in Dashboard)

**Sub-batch:** 8b (moderate)

---

## Module Metadata

| Key | Value |
|-----|-------|
| Module path | `frontend/src/features/notifications/ResubmitModal.tsx` |
| Test path | `frontend/tests/unit/features/notifications/ResubmitModal.test.tsx` |
| API module | `frontend/src/api/notifications.ts` |
| Hook | `frontend/src/features/notifications/useResubmit.ts` |
| FRs | FR-018, FR-019 |
| Exports | `ResubmitModal`, `useResubmit` |

---

## Imports

| Symbol | Source module |
|--------|--------------|
| `apiClient` | `src/api/client.ts` |
| `createResubmitRequest`, `listResubmitRequests` | `src/api/notifications.ts` |
| `useAuthStore` | `src/stores/auth-store.ts` |
| `ErrorDisplay` | `src/components/ErrorDisplay.tsx` |
| `useTranslation` | `react-i18next` |

---

## FRs

**FR-018 — Notify Resubmit**
- FinanceAdmin or UplineReviewer triggers resubmit notification for a specific filing unit.
- Required inputs (from Dashboard context): `cycle_id`, `org_unit_id`, `reason` (free text), `target_version` (optional — the version to resubmit against), `requester_user_id` (from auth store), `recipient_user_id`, `recipient_email`.
- Backend sends Email to the filing-unit manager with explanation and template download link.
- Error `NOTIFY_001` (502): SMTP unreachable — notification not sent; show error.
- Error `NOTIFY_002` (500): audit log write failed — notification NOT sent; show error. This is a hard failure.

**FR-019 — Resubmit Record**
- Every resubmit request is persisted before notification is sent.
- Record fields: `id`, `cycle_id`, `org_unit_id`, `requester_id`, `target_version` (optional), `reason`, `requested_at`.
- Dashboard marks the org unit with "已通知重傳" status after request created.
- History of all resubmit requests for a unit is queryable via `GET /resubmit-requests?cycle_id=&org_unit_id=`.
- Error `NOTIFY_002`: if the DB record write fails, the notification is NOT sent (atomicity guarantee). Frontend must display this error clearly.

---

## Exports

- `ResubmitModal` — Mantine Modal component. Accepts props:
  ```typescript
  interface ResubmitModalProps {
    opened: boolean;
    onClose: () => void;
    cycleId: string;
    orgUnitId: string;
    orgUnitName: string;
    recipientUserId: string;
    recipientEmail: string;
    latestVersion: number | null;
  }
  ```
- `useResubmit` — wraps `createResubmitRequest()` mutation and `listResubmitRequests()` query.

---

## API Calls

| # | Method | Endpoint | Request | Response |
|---|--------|----------|---------|----------|
| 1 | POST | `/resubmit-requests` | `{ cycle_id, org_unit_id, reason, target_version?, requester_user_id, recipient_user_id, recipient_email }` | 201 `ResubmitRequestRead` |
| 2 | GET | `/resubmit-requests` | `?cycle_id=&org_unit_id=` | `ResubmitRequestRead[]` |

**`ResubmitRequestRead` shape:**
```typescript
{
  id: string;
  cycle_id: string;
  org_unit_id: string;
  requester_id: string;
  target_version: number | null;
  reason: string;
  requested_at: string;   // ISO-8601 UTC
}
```

**Note:** The endpoint is flat `POST /resubmit-requests` (not nested under cycles). This is the corrected path per build plan ambiguity resolution #5.

---

## UI States

| State | UI |
|-------|----|
| **Modal closed** | Not rendered |
| **Modal open — history loading** | Skeleton in the history section while `listResubmitRequests` loads |
| **Modal open — submitting** | Submit button shows spinner; form fields disabled |
| **Modal open — error** | `<ErrorDisplay error={err} />` above the form |
| **Modal open — success** | Close modal; Dashboard row status updates to "已通知重傳" |
| **History empty** | "尚無重傳紀錄" text in history section |
| **History populated** | Table of past requests: requested_at, reason (truncated), requester, target_version |

---

## User Interactions

1. **Open modal** — triggered by "通知重傳" button in a Dashboard row (Dashboard owns the open/close state).
2. **Reason input** — required text area. Minimum 1 character. react-hook-form + zod validation.
3. **Target version** — optional number input. Pre-filled with `latestVersion` prop if provided.
4. **Submit** — calls `createResubmitRequest(...)`. `requester_user_id` injected from `useAuthStore().user.user_id`.
5. **History tab / section** — within the modal, a read-only section loads `listResubmitRequests({ cycleId, orgUnitId })` showing all previous resubmit requests for this unit in this cycle.
6. **Close** — "取消" button or backdrop click; dirty form shows unsaved-changes confirmation.

---

## Side-Effects

- `createResubmitRequest` mutation: on success, invalidates `['dashboard', cycleId]` so the Dashboard status grid reflects "已通知重傳" immediately. Also invalidates `['resubmitRequests', cycleId, orgUnitId]`.
- `listResubmitRequests` is fetched when the modal opens (enabled when `opened === true`).

---

## Verbatim Status Strings

- Dashboard row status after resubmit: `t('dashboard.status.resubmit')` — "已通知重傳"

---

## Gotchas

- This is a **feature component**, not a page. It lives in `src/features/notifications/`, not `src/pages/`. Dashboard imports it directly: `import { ResubmitModal } from '../features/notifications/ResubmitModal'` (no barrel export from `features/`).
- `requester_user_id` must come from `useAuthStore().user.user_id`, never from props (security: cannot allow the caller to spoof the requester identity).
- `recipient_email` is passed from the Dashboard row data (the filing-unit manager's email, which comes from the dashboard API response). The modal does NOT fetch it independently.
- `NOTIFY_002` is the most important error to surface clearly: it means the resubmit was NOT logged AND NOT sent — user must be told to retry.
- `reason` is free text with no prescribed max length on the frontend; keep the textarea flexible.
- The modal must be accessible: focus moves to the modal on open; escape key closes it; focus returns to the trigger button on close.

---

## Tests

1. **Renders form with reason textarea and optional target_version input** — mount modal in `opened` state; assert form fields present.
2. **Submits createResubmitRequest with correct payload including auth user_id** — mock auth store with `user_id: 'user-123'`; fill reason; submit; assert mutation called with `requester_user_id: 'user-123'`.
3. **Shows ErrorDisplay on NOTIFY_002** — mock `createResubmitRequest` returning 500 `{ error: { code: 'NOTIFY_002' } }`; assert `ErrorDisplay` rendered with specific error.
4. **History section shows list of past requests** — mock `listResubmitRequests` returning 2 entries; assert both rows rendered in history table.
5. **Form validation prevents empty reason submission** — submit without filling reason; assert validation error shown and mutation not called.

---

## Consistency Constraints

- **FCR-001:** This module uses the shared `apiClient` from `src/api/client.ts` for all HTTP requests. It does NOT create its own axios instance or use raw `fetch()`. The CSRF token is read from `document.cookie` and set as `X-CSRF-Token` by the request interceptor.
- **FCR-004:** All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
- **FCR-005:** API errors caught by mutation `onError` callbacks are passed to `<ErrorDisplay error={err} />`. The component is NOT duplicated or reimplemented locally.
- **FCR-007:** Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
- **FCR-009:** The API function in `notifications.ts` defines a zod schema for the response and calls `.parse()` or `.safeParse()` on `response.data` before returning.
- **FCR-011:** This module does not read `bc_session` or `bc_refresh` cookies. It does not write to `localStorage` or `sessionStorage` for auth purposes.
- **FCR-013:** Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
