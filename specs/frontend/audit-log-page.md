# Spec: Audit Log Search Page (`/audit`)

**Sub-batch:** 8a (simple)

---

## Module Metadata

```
Module:    frontend/src/pages/audit/AuditLogPage.tsx
Test path: frontend/tests/unit/pages/audit/AuditLogPage.test.tsx
API module:  frontend/src/api/audit.ts
Hook:      frontend/src/features/audit/useAuditLogs.ts
FRs:       FR-023
Exports:   AuditLogPage, useAuditLogs
```

---

## Imports

| Symbol | Source module |
|--------|--------------|
| `apiClient` | `src/api/client.ts` |
| `DataTable` | `src/components/DataTable.tsx` |
| `ErrorDisplay` | `src/components/ErrorDisplay.tsx` |
| `downloadBlob` | `src/lib/download.ts` |
| `useAuthStore` | `src/stores/auth-store.ts` |
| `useTranslation` | `react-i18next` |

---

## FRs

**FR-023 — Audit Log**
- Complete operational log of all actions (login/logout, template download, file upload, personnel import, shared-cost import, notification sent).
- Every entry includes: user ID, timestamp, IP address, action, resource type, resource ID, and content summary.
- Tamper-proof (append-only with hash chain on backend).
- Retention: at least 5 years.
- Supports multi-condition filtering: `user_id`, `action`, `resource_type`, `resource_id`, date range `from`/`to`.
- Chain integrity verifiable via `GET /audit-logs/verify`.
- CSV export via `GET /audit-logs/export?from=&to=`.

---

## API Calls

| # | Method | Endpoint | Request | Response |
|---|--------|----------|---------|----------|
| 1 | GET | `/audit-logs` | query: `?user_id=&action=&resource_type=&resource_id=&from=&to=&page=&size=` | `{ items: AuditLogRead[], total, page, size }` |
| 2 | GET | `/audit-logs/verify` | query: `?from=&to=` | `{ verified: bool, range: [datetime?, datetime?], chain_length: int }` |
| 3 | GET | `/audit-logs/export` | query: `?from=&to=` | CSV binary stream (Content-Disposition: attachment) |

**`AuditLogRead` shape:**
```typescript
{
  id: string;           // UUID
  user_id: string;      // UUID
  action: string;       // e.g. "budget_upload.accepted"
  resource_type: string;
  resource_id: string | null;
  ip_address: string;
  timestamp: string;    // ISO-8601 UTC
  details: Record<string, unknown> | null;
}
```

---

## UI States

| State | UI |
|-------|----|
| **Loading** | `DataTable` with Mantine skeleton rows (5 rows) while query is in-flight |
| **Error** | `<ErrorDisplay error={err} />` — covers AUDIT_002 (bad filter params) and SYS_001 |
| **Empty** | Descriptive message: `t('audit.empty.no_results')` with suggestion to widen date range |
| **Populated** | Paginated `DataTable` with columns: timestamp, user_id, action, resource_type, resource_id, ip_address |

---

## User Interactions

1. **Filter form** — `user_id` text input, `action` select, `resource_type` select, `resource_id` text input, `from` / `to` date pickers. Submit triggers `useAuditLogs` refetch with updated params.
2. **Pagination** — `page` / `size` controlled by DataTable; changes trigger query refetch.
3. **Verify chain** — "驗證完整性" button calls `verifyChain(from, to)`. Shows modal with `verified: true/false`, `chain_length`, date range.
4. **Export CSV** — "匯出 CSV" button calls `downloadBlob('/audit-logs/export?from=&to=', 'audit-log.csv')` with current date range filters.

---

## Side-Effects

- `useAuditLogs` wraps `GET /audit-logs` in a `useQuery`; no `refetchInterval` (read-only, no polling required).
- CSV export uses `downloadBlob` from shared helper (FCR-008).
- No mutations — ITSecurityAuditor has no write permissions.

---

## Gotchas

- Role guard: only `ITSecurityAuditor` may access `/audit`. `<RouteGuard roles={["ITSecurityAuditor"]}>`.
- The `from` / `to` date range is required for export and verify; show inline validation if missing.
- Error code `AUDIT_002` (400) means invalid filter parameters — show via `ErrorDisplay`, not a page crash.
- `action` values are snake_case event strings from the backend (e.g., `"budget_upload.accepted"`) — display as-is in English (technical labels per NFR-USE-001).
- Large export requests are streaming CSV — `downloadBlob` must handle `responseType: 'blob'` on the axios call in `audit.ts`.

---

## Tests

1. **Renders filter form and empty DataTable skeleton while loading** — mock `queryAuditLogs` pending; assert skeleton rows present and submit button disabled.
2. **Displays paginated results on success** — mock returns `{ items: [...3 logs...], total: 3, page: 1, size: 50 }`; assert table rows appear with correct timestamp, action, ip_address.
3. **Shows ErrorDisplay on AUDIT_002 error** — mock returns 400 `{ error: { code: 'AUDIT_002', message: '...' } }`; assert `<ErrorDisplay>` rendered.
4. **Shows empty state message when no results** — mock returns `{ items: [], total: 0, page: 1, size: 50 }`; assert `t('audit.empty.no_results')` visible.
5. **Export CSV button calls downloadBlob with correct URL** — spy on `downloadBlob`; click export button; assert called with URL containing `from` and `to` params.

---

## Constraints

- **FCR-001:** This module uses the shared `apiClient` from `src/api/client.ts` for all HTTP requests. It does NOT create its own axios instance or use raw `fetch()`. The CSRF token is read from `document.cookie` and set as `X-CSRF-Token` by the request interceptor.
- **FCR-002:** This page component is wrapped in `<RouteGuard roles={["ITSecurityAuditor"]}>`. The route appears in the sidebar only for that role.
- **FCR-004:** All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
- **FCR-005:** API errors caught by mutation `onError` callbacks are passed to `<ErrorDisplay error={err} />`. The component is NOT duplicated or reimplemented locally.
- **FCR-008:** File downloads in this component use `downloadBlob()` or `pollAndDownload()` from `src/lib/download.ts`. No manual `window.open()`, `a.click()`, or direct blob handling.
- **FCR-009:** The API function in `audit.ts` defines a zod schema for the response and calls `.parse()` or `.safeParse()` on `response.data` before returning.
- **FCR-010:** This page checks `isLoading`, `isError`, and `data?.items.length === 0` from its query hook and renders appropriate UI for each state.
- **FCR-013:** Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
