# Spec: Dashboard Page (`/dashboard`)

**Sub-batch:** 8c (complex)

---

## Module Metadata

| Key | Value |
|-----|-------|
| Module path | `frontend/src/pages/dashboard/DashboardPage.tsx` |
| Test path | `frontend/tests/unit/pages/dashboard/DashboardPage.test.tsx` |
| API modules | `frontend/src/api/dashboard.ts`, `frontend/src/api/notifications.ts` |
| Hook | `frontend/src/features/consolidated-report/useDashboard.ts` |
| FRs | FR-004, FR-014 |
| Exports | `DashboardPage`, `useDashboard` |

---

## Imports

| Symbol | Source module |
|--------|--------------|
| `apiClient` | `src/api/client.ts` |
| `getDashboard` | `src/api/dashboard.ts` |
| `listFailedNotifications`, `resendNotification` | `src/api/notifications.ts` |
| `ResubmitModal` | `src/features/notifications/ResubmitModal.tsx` |
| `StatusBadge` | `src/components/StatusBadge.tsx` |
| `DataTable` | `src/components/DataTable.tsx` |
| `ErrorDisplay` | `src/components/ErrorDisplay.tsx` |
| `useAuthStore` | `src/stores/auth-store.ts` |
| `useTranslation` | `react-i18next` |

---

## FRs

**FR-004 — Monitor Cycle Progress**
- Dashboard shows each filing unit's status: 未下載 / 已下載 / 已上傳 / 已通知重傳.
- Refresh frequency: status changes reflected within ≤ 5 seconds.
- Manual refresh button also available.
- If no filing units (cycle not open): show "尚未開放週期" prompt.
- Data source connection failure: show "資料更新中" and retain last successful snapshot.

**FR-014 — Filing Status Dashboard**
- Role-differentiated view:
  - **FinanceAdmin**: sees all filing units across the entire company; can trigger resubmit.
  - **UplineReviewer** (1000/0800/0500): sees only units within their org scope (backend scopes response).
  - **CompanyReviewer (0000)**: no upload status list; only sees a link to the consolidated report. Dashboard renders a redirect/banner pointing to `/reports`.
  - **FilingUnitManager**: NOT a dashboard consumer (no dashboard nav item).
- Supports filtering by `status` and `org_unit_id`.
- Shows summary cards: total, uploaded count, not_downloaded count, downloaded count, resubmit_requested count.
- Shows last uploaded timestamp and version number per row.
- `data_freshness.stale`: when true, show "資料更新中" banner with stale snapshot.
- Failed notification section (FinanceAdmin only): collapsible section listing `FailedNotificationItem[]` with resend capability.

---

## Exports

- `DashboardPage` — page component.
- `useDashboard` — TanStack Query hook wrapping `getDashboard()` with 5-second polling.

---

## API Calls

| # | Method | Endpoint | Request | Response |
|---|--------|----------|---------|----------|
| 1 | GET | `/cycles/{cycle_id}/dashboard` | `?status=&org_unit_id=&limit=&offset=` | `DashboardResponse` |
| 2 | GET | `/notifications/failed` | — | `{ items: FailedNotificationItem[] }` |
| 3 | POST | `/notifications/{id}/resend` | `{ recipient_email: string }` | `{ id, status, bounce_reason? }` |

**`DashboardResponse` shape:**
```typescript
{
  cycle: {
    id: string;
    fiscal_year: number;
    deadline: string;
    status: 'Open' | 'Closed';
  };
  items: DashboardItem[];
  summary: {
    total: number;
    uploaded: number;
    not_downloaded: number;
    downloaded: number;
    resubmit_requested: number;
  };
  data_freshness: {
    snapshot_at: string;   // ISO-8601 UTC
    stale: boolean;
  };
}

interface DashboardItem {
  org_unit_id: string;
  org_unit_name: string;
  status: 'not_downloaded' | 'downloaded' | 'uploaded' | 'resubmit_requested';
  last_uploaded_at: string | null;
  version: number | null;
  recipient_user_id: string;
  recipient_email: string;
}
```

**`FailedNotificationItem` shape:**
```typescript
{
  id: string;
  type: string;
  recipient_id: string;
  status: string;
  bounce_reason: string | null;
  created_at: string;
}
```

---

## UI States

### Global States

| State | UI |
|-------|----|
| **Loading (initial)** | Full-page skeleton: summary card skeletons (4 cards) + table skeleton rows |
| **Error** | `<ErrorDisplay error={err} />` with manual retry button |
| **Stale data** | Yellow banner: `t('dashboard.freshness.stale')` — "資料更新中，顯示最後成功快照" |
| **No Open Cycle** | "尚未開放週期" centered message with link to Cycle Admin (FinanceAdmin only) |
| **CompanyReviewer** | No status grid; show banner: `t('dashboard.company_reviewer.report_link')` with link to `/reports` |

### Status Grid States

| State | UI |
|-------|----|
| **Empty (no items)** | "目前無填報單位資料" message |
| **Populated** | DataTable with status filter, per-row `StatusBadge`, "通知重傳" button |

### Failed Notifications Section (FinanceAdmin only)

| State | UI |
|-------|----|
| **Loading** | Skeleton |
| **Empty** | "無失敗通知" collapsed section |
| **Populated** | Collapsible Mantine Accordion section listing failed items with "重送" button per row |

---

## User Interactions

1. **Cycle selector dropdown** — auto-selects latest Open cycle on mount. Dropdown allows switching to other cycles (including Closed, for historical view). Changing cycle refetches dashboard with new `cycle_id`.

2. **Status filter** — Select dropdown: All / 未下載 / 已下載 / 已上傳 / 已通知重傳. On change: refetch dashboard with `?status=` param.

3. **Org unit filter** — optional text search input filtering by `org_unit_name` (client-side filter on returned items, or pass `?org_unit_id=` if exact match).

4. **Manual refresh** — "重新整理" icon button calls `refetch()` immediately.

5. **Resubmit** — "通知重傳" button in each row (visible to FinanceAdmin and UplineReviewer). Opens `<ResubmitModal>` with the row's `org_unit_id`, `org_unit_name`, `recipient_user_id`, `recipient_email`, `version`.

6. **Resend failed notification** — "重送" button in failed notifications section. Opens email input dialog (pre-filled with original recipient email). On confirm: `POST /notifications/{id}/resend` with `{ recipient_email }`.

7. **Summary cards** — four summary stat cards (total, uploaded, not_downloaded, resubmit_requested) from `DashboardResponse.summary`. Clicking a card filters the status grid by that status (optional enhancement, but cards are always visible).

---

## Side-Effects

- **Polling:** `useDashboard` sets `refetchInterval: 5000` and `refetchIntervalInBackground: false` on the `useQuery` call. No `setInterval` or manual polling loops.
- **Stale detection:** when `data_freshness.stale === true`, render the "資料更新中" banner. Continue polling even when stale.
- **Cycle resolution:** on mount, fetch `GET /cycles?status=Open` to find the default cycle. Store selected `cycleId` in local React state (not Zustand — it's page-local UI state). When user switches cycle via dropdown, update local state → triggers dashboard refetch.
- **ResubmitModal close:** on success, invalidates `['dashboard', cycleId]` query (causing immediate re-fetch).
- **Resend notification:** `resendNotification` mutation invalidates `['failedNotifications']`.

---

## Verbatim Status Strings

Status values from `DashboardItem.status` must be displayed via i18n:

| API value | i18n key | Display text |
|-----------|----------|--------------|
| `not_downloaded` | `dashboard.status.not_downloaded` | "未下載" |
| `downloaded` | `dashboard.status.downloaded` | "已下載" |
| `uploaded` | `dashboard.status.uploaded` | "已上傳" |
| `resubmit_requested` | `dashboard.status.resubmit_requested` | "已通知重傳" |

Summary card labels:
- `t('dashboard.summary.total')` — "填報單位總數"
- `t('dashboard.summary.uploaded')` — "已上傳"
- `t('dashboard.summary.not_downloaded')` — "未下載"
- `t('dashboard.summary.resubmit_requested')` — "已通知重傳"

Freshness banner: `t('dashboard.freshness.stale')` — "資料更新中，顯示最後成功快照"
No-cycle prompt: `t('dashboard.no_cycle.prompt')` — "尚未開放週期"

---

## Gotchas

- Route guard: `<RouteGuard roles={["FinanceAdmin", "UplineReviewer", "CompanyReviewer"]}>`. CompanyReviewer sees a limited view (report link banner only).
- The `hook path` in the build plan is `src/features/consolidated-report/useDashboard.ts` — note the feature folder name is `consolidated-report` even though this is the dashboard hook. Follow the build plan exactly.
- **FCR-006 is critical here:** polling MUST be `refetchInterval: 5000` + `refetchIntervalInBackground: false`. No deviations.
- When `data_freshness.stale` is true, do NOT clear the displayed data — retain the last successful snapshot.
- CompanyReviewer (0000) has no `org_unit_id` scope; the backend returns an empty `items[]` for them, and the frontend should detect CompanyReviewer role and show the report link banner instead of the empty state.
- The failed notifications section uses `GET /notifications/failed` (no `cycle_id` filter — it's global across all notification types). Only render this section when `useAuthStore().hasRole('FinanceAdmin')`.
- `DashboardPage` is the largest page component. If it approaches 400 lines, extract sub-components: `SummaryCards`, `StatusGrid`, `FailedNotificationsPanel`.
- `ResubmitModal` is imported directly from `src/features/notifications/ResubmitModal.tsx` — not from a barrel export.

---

## Tests

1. **Renders summary cards and status grid on success** — mock `getDashboard` returning full `DashboardResponse` with 3 items; assert 4 summary cards visible with correct counts; assert 3 table rows with correct status badges.
2. **Polling configured correctly** — assert `useQuery` is called with `refetchInterval: 5000` and `refetchIntervalInBackground: false`; verify no `setInterval` call in component.
3. **Stale data banner shown** — mock `getDashboard` returning `data_freshness: { stale: true }`; assert "資料更新中" banner rendered; assert data still displayed (not cleared).
4. **CompanyReviewer sees report link, not status grid** — mock auth store with role `CompanyReviewer`; assert status grid NOT rendered; assert report link banner visible.
5. **Resubmit modal opens on button click** — mock `getDashboard` with one item; click "通知重傳" in that row; assert `ResubmitModal` rendered with correct `orgUnitId` prop.
6. **Failed notifications section visible to FinanceAdmin only** — mock auth store as `FinanceAdmin`; mock `listFailedNotifications` with 2 items; assert section visible. Re-render as `UplineReviewer`; assert section NOT rendered.

---

## Consistency Constraints

- **FCR-001:** This module uses the shared `apiClient` from `src/api/client.ts` for all HTTP requests. It does NOT create its own axios instance or use raw `fetch()`. The CSRF token is read from `document.cookie` and set as `X-CSRF-Token` by the request interceptor.
- **FCR-002:** This page component is wrapped in `<RouteGuard roles={["FinanceAdmin", "UplineReviewer", "CompanyReviewer"]}>`. The route appears in the sidebar only for those roles.
- **FCR-003:** This component references status colors via the theme object or via `StatusBadge`. No hardcoded hex color strings for status indicators.
- **FCR-004:** All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
- **FCR-005:** API errors caught by mutation `onError` callbacks are passed to `<ErrorDisplay error={err} />`. The component is NOT duplicated or reimplemented locally.
- **FCR-006:** The `useQuery` call for dashboard data sets `refetchInterval: 5000` and `refetchIntervalInBackground: false`. No `setInterval` or manual polling loops.
- **FCR-007:** Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
- **FCR-009:** The API function in `dashboard.ts` and `notifications.ts` defines a zod schema for the response and calls `.parse()` or `.safeParse()` on `response.data` before returning.
- **FCR-010:** This page checks `isLoading`, `isError`, and `data?.items.length === 0` from its query hook and renders appropriate UI for each state.
- **FCR-011:** This module does not read `bc_session` or `bc_refresh` cookies. It does not write to `localStorage` or `sessionStorage` for auth purposes.
- **FCR-013:** Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
