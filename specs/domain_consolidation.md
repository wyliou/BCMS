# Spec: domain/consolidation (M7)

**Batch:** 6
**Complexity:** Complex

## 1. Module Paths & Test Paths

| File | Test |
|---|---|
| `backend/src/app/domain/consolidation/dashboard.py` | `backend/tests/unit/consolidation/test_dashboard.py`, `backend/tests/integration/consolidation/test_dashboard.py` |
| `backend/src/app/domain/consolidation/report.py` | `backend/tests/unit/consolidation/test_report.py` |
| `backend/src/app/domain/consolidation/export.py` | `backend/tests/integration/consolidation/test_export.py` |
| `backend/src/app/api/v1/dashboard.py` | `backend/tests/api/test_dashboard.py` |
| `backend/src/app/api/v1/reports.py` | `backend/tests/api/test_reports.py` |

---

## 2. Functional Requirements

### FR-004 — Per-role Dashboard Status

- **Status values per filing unit:** `not_downloaded` / `downloaded` / `uploaded` / `resubmit_requested`.
  - `not_downloaded`: Template exists but `ExcelTemplate.download_count == 0`.
  - `downloaded`: Template downloaded but no budget upload exists.
  - `uploaded`: A `BudgetUpload` row exists for the latest cycle and this org unit.
  - `resubmit_requested`: An open `ResubmitRequest` exists for this org unit and cycle.
- **Scoped:** Uses `RBAC.scoped_org_units(user, db)` — each role sees only its scope (CR-011).
- **Empty cycle sentinel:** If no Open cycle exists (or cycle has no filing units), return `DashboardResponse(sentinel='尚未開放週期', items=[])`.
- **Performance:** ≤5s after state change. Implementation uses a single SQL join (not N+1); the query covers `org_units`, `excel_templates`, `budget_uploads`, and `resubmit_requests`.
- **Stale fallback (FR-014):** If the DB query raises an `InfraError` (connection issue), the service falls back to the last materialized snapshot (if any) and returns `DashboardResponse(items=..., stale=True)`. If no snapshot exists, raise `InfraError`.
- **`0000公司` Reviewer (FR-014):** `CompanyReviewer` role sees a summary-only dashboard — `items=[]`, `summary` field only. No individual filing-unit rows.

### FR-014 — Role-scoped Dashboard (detailed)

- **Filters:** `status` (optional, one of the four values), `org_unit_id` (optional).
- **Sorting:** `uploaded_at` desc by default; configurable.
- **Pagination:** `limit` + `offset`.
- **Shows:** Last upload time (`last_uploaded_at`) + `version` for each filing unit.
- **≤5s reflection:** State changes from uploads must appear within 5 seconds. No cache with TTL > 5s.

### FR-015 — Consolidated Report (three-source join)

- `ConsolidatedReportService.build(cycle_id, scope)` joins:
  - Latest `BudgetUpload` lines (operational budget) via `BudgetUploadService.get_latest_by_cycle`.
  - Latest `PersonnelBudgetUpload` lines (personnel budget) via `PersonnelImportService.get_latest_by_cycle`.
  - Latest `SharedCostUpload` lines (shared cost) via `SharedCostImportService.get_latest_by_cycle`.
- Joined on `(org_unit_id, account_code_id)`.
- Returns three `last_updated_at` timestamps (one per source) — the `uploaded_at` of the latest version for each source in this cycle.
- **Level threshold for personnel/shared_cost columns (CR-016):** `personnel_budget` and `shared_cost` columns are populated ONLY for rows whose `org_unit.level_code IN ('1000', '0800', '0500', '0000')`. For lower levels (`4000`, `2000`, `6000`, `5000`), these columns are `null`.
- **RBAC scoping (CR-011):** Service calls `RBAC.scoped_org_units(user, db)` and filters rows to this scope.

### FR-016 — Per-row Computed Fields

- `actual`: From `actual_expenses` table for `(cycle_id, org_unit_id, account_code_id)`.
- `delta_amount = operational_budget - actual` (when `operational_budget` is available and actual is known).
- `delta_pct` (CR-013, CR-014):
  - When `actual == 0` (or `None`): `delta_pct = 'N/A'`.
  - Otherwise: `delta_pct = Decimal(delta_amount) / Decimal(actual)`, quantized to 1 decimal place using `ROUND_HALF_UP`, serialized as string (e.g. `'9.1'`).
- `budget_status` (CR-015):
  - `'not_uploaded'` when no `BudgetUpload` exists for this `(cycle_id, org_unit_id)`.
  - `operational_budget = null` in that case.

### FR-017 — Export

- **Sync path:** `len(scoped_org_units) <= BC_ASYNC_EXPORT_THRESHOLD` → `export_async` builds the workbook synchronously, saves via `infra.storage.save`, returns `201 + {file_url, expires_at}`.
- **Async path:** Otherwise, enqueues a job via `infra.jobs.enqueue(handler='report_export', payload={...})`, returns `202 + {job_id}`.
- **Job completion:** `ReportExportHandler.run` (registered with `infra.jobs`) builds the report, saves the file, sends email to requester via `NotificationService.send(NotificationTemplate.report_ready, ...)`.
- **Failure (REPORT_002):** If the export job fails (exception in `ReportExportHandler.run`), raise `AppError(code='REPORT_002')`. The job framework marks the run as `failed`.
- **`unsubmitted_for_cycle` import (CR-026):** `DashboardService` imports `infra.db.repos.budget_uploads_query.unsubmitted_for_cycle` for the "not uploaded" status determination.

---

## 3. Exports

```python
# domain/consolidation/dashboard.py

async def status_for_user(
    cycle_id: UUID,
    user: User,
    filters: DashboardFilters | None = None,
) -> DashboardResponse:
    """Return the role-scoped dashboard for a user and cycle.

    Computes per-filing-unit status (not_downloaded/downloaded/uploaded/
    resubmit_requested) from a single SQL join. Falls back to stale snapshot
    on InfraError. CompanyReviewer receives summary-only response.

    Args:
        cycle_id: UUID of the cycle. If no Open cycle, returns sentinel.
        user: Authenticated user (scope applied from role).
        filters: Optional status/org_unit_id filter + sort + pagination.

    Returns:
        DashboardResponse: Items list (scoped), optional stale flag, optional sentinel.
    """

# domain/consolidation/report.py

async def build(
    cycle_id: UUID,
    scope: ReportScope,
) -> ConsolidatedReport:
    """Build the consolidated report for a cycle scoped to the requesting user.

    Joins latest budget_uploads + personnel_uploads + shared_cost_uploads
    by (org_unit, account_code). Personnel and shared_cost columns populated
    only for org units at level 1000 or above (CR-016).

    Args:
        cycle_id: UUID of the cycle.
        scope: ReportScope containing user + RBAC-resolved org_unit set.

    Returns:
        ConsolidatedReport: Rows with actual, delta_amount, delta_pct (CR-013/014),
            budget_status (CR-015), and three last_updated_at timestamps.
    """

# domain/consolidation/export.py

async def export_async(
    cycle_id: UUID,
    scope: ReportScope,
    format: ExportFormat,
    user: User,
) -> ExportEnqueueResult:
    """Trigger report export (sync or async based on scope size).

    If len(scope.org_unit_ids) <= BC_ASYNC_EXPORT_THRESHOLD, builds and saves
    synchronously and returns 201 + file_url. Otherwise enqueues a durable job
    and returns 202 + job_id.

    Args:
        cycle_id: UUID of the cycle.
        scope: RBAC-resolved scope.
        format: ExportFormat enum (e.g. 'xlsx').
        user: Requesting user (for job completion notification).

    Returns:
        ExportEnqueueResult: sync_url + expires_at (sync), OR job_id (async).

    Raises:
        AppError(REPORT_002): Synchronous export build failed.
    """

# ReportExportHandler.run (registered with infra.jobs at startup)

async def run(job_payload: dict) -> dict:
    """Execute a deferred report export job.

    Reads cycle_id, scope, format, user_id from payload. Builds the report,
    saves the file via infra.storage, emails the requester via
    NotificationService, marks the job run completed.

    Args:
        job_payload: dict with keys cycle_id, scope_org_unit_ids, format, user_id.

    Returns:
        dict: {'file_url': str, 'expires_at': str ISO-8601}.

    Raises:
        AppError(REPORT_002): Build or storage failure; job framework marks run failed.
    """
```

**Pydantic models:**
```python
class DashboardItem(BaseModel):
    org_unit_id: UUID
    org_unit_name: str
    status: Literal["not_downloaded", "downloaded", "uploaded", "resubmit_requested"]
    last_uploaded_at: datetime | None
    version: int | None

class DashboardResponse(BaseModel):
    items: list[DashboardItem]
    sentinel: str | None = None
    stale: bool = False
    summary: dict | None = None  # populated for CompanyReviewer only

class ConsolidatedReportRow(BaseModel):
    org_unit_id: UUID
    org_unit_name: str
    account_code: str
    account_name: str
    actual: Decimal | None
    operational_budget: Decimal | None
    personnel_budget: Decimal | None  # null for levels below 1000 (CR-016)
    shared_cost: Decimal | None       # null for levels below 1000 (CR-016)
    delta_amount: Decimal | None
    delta_pct: str  # '9.1', 'N/A', or null (CR-013, CR-014)
    budget_status: Literal["not_uploaded", "uploaded"]

class ConsolidatedReport(BaseModel):
    cycle_id: UUID
    rows: list[ConsolidatedReportRow]
    budget_last_updated_at: datetime | None
    personnel_last_updated_at: datetime | None
    shared_cost_last_updated_at: datetime | None

class ReportScope(BaseModel):
    user_id: UUID
    org_unit_ids: set[UUID]

class ExportFormat(StrEnum):
    xlsx = "xlsx"

class ExportEnqueueResult(BaseModel):
    sync: bool
    file_url: str | None = None
    expires_at: datetime | None = None
    job_id: UUID | None = None
```

---

## 4. Imports

| Module | Symbols | Called by |
|---|---|---|
| `domain.cycles` | `CycleService.get`, `CycleService.get_status` | `status_for_user` (check Open state), `build` |
| `domain.budget_uploads` | `BudgetUploadService.get_latest_by_cycle` | `report.build` — operational budget join |
| `domain.personnel` | `PersonnelImportService.get_latest_by_cycle` | `report.build` — personnel budget join (CR-016) |
| `domain.shared_costs` | `SharedCostImportService.get_latest_by_cycle` | `report.build` — shared cost join (CR-016) |
| `domain.accounts` | `AccountService.list` | `report.build` — account code names |
| `domain.audit` | `AuditService.record`, `AuditAction` | Export events |
| `core.security` | `User`, `Role`, `RBAC` | `status_for_user`, `build` — scope resolution (CR-011) |
| `infra.db` | `get_session`, `AsyncSession` | All service methods |
| `infra.db.repos.budget_uploads_query` | `unsubmitted_for_cycle` | `status_for_user` — 'not uploaded' status (CR-026) |
| `infra.jobs` | `enqueue`, `register_handler` | `export_async` async path; `ReportExportHandler` registration |
| `infra.excel` | `write_workbook`, `workbook_to_bytes` | Export workbook construction |
| `infra.storage` | `save` | Export file storage |
| `core.errors` | `AppError`, `InfraError` | Error raising |
| `core.clock` | `now_utc` | `expires_at` calculation, timestamp comparisons |

### Required Call Order in `ConsolidatedReportService.build` (FR-015, FR-016)

1. `scoped = scope.org_unit_ids` — already RBAC-resolved by the route layer.
2. `budget_map = await budget_upload_service.get_latest_by_cycle(cycle_id)`.
3. `personnel_map = await personnel_service.get_latest_by_cycle(cycle_id)`.
4. `shared_cost_map = await shared_cost_service.get_latest_by_cycle(cycle_id)`.
5. Fetch all `actual_expenses` for `(cycle_id, org_unit_id IN scoped)`.
6. Fetch all `OrgUnit` rows for `scoped` set (with `level_code`).
7. For each `(org_unit_id, account_code_id)` in the union of all four sources:
   - Populate `actual`, `operational_budget`, `personnel_budget` (if level ≥ 1000, CR-016), `shared_cost` (if level ≥ 1000, CR-016).
   - Compute `delta_amount = operational_budget - actual` if both not null.
   - Compute `delta_pct` per CR-013/CR-014.
   - Set `budget_status` per CR-015.
8. Compute three `last_updated_at` timestamps from the `uploaded_at` of the max-version rows.
9. Return `ConsolidatedReport`.

---

## 5. Side Effects

- Reads from `excel_templates`, `budget_uploads`, `personnel_budget_uploads`, `shared_cost_uploads`, `actual_expenses`, `resubmit_requests` tables.
- May write `dashboard_snapshots` table (stale fallback).
- `export_async` (sync path): saves `.xlsx` to `infra.storage`.
- `export_async` (async path): enqueues a `job_runs` row via `infra.jobs`.
- `ReportExportHandler.run`: saves file + sends email notification.
- Writes `audit_logs` on export.

---

## 6. Gotchas

- **CR-013 — `delta_pct` must use `ROUND_HALF_UP` with `Decimal`.** `from decimal import Decimal, ROUND_HALF_UP`. Never `float` division. Test case: `delta=100, actual=1100 → '9.1'` not `'9.09'`.
- **CR-014 — `delta_pct = 'N/A'` when `actual == 0` or `actual is None`.** Not `null`, not `0.0`, not a missing key. The field is always present.
- **CR-015 — `budget_status = 'not_uploaded'` and `operational_budget = null`.** The row exists in the report even for non-uploaded units. Never omit or substitute zero.
- **CR-016 — Personnel/shared_cost columns only for level ≥ 1000.** Compare `org_unit.level_code IN ('1000', '0800', '0500', '0000')`. For all other levels, set `personnel_budget = null` and `shared_cost = null`. This is NOT about whether data exists — it is a display rule.
- **CR-011 — RBAC scope is applied before any data access.** `ReportScope.org_unit_ids` comes from `RBAC.scoped_org_units(user, db)` called in the route layer. The service trusts this set.
- **CR-026 — Use `infra.db.repos.budget_uploads_query.unsubmitted_for_cycle`.** Do not write a new SQL join for the unsubmitted check in the dashboard.
- **CompanyReviewer dashboard:** Returns `DashboardResponse(items=[], summary={...})`. The `summary` field contains company-wide aggregate totals (total units, total uploaded, etc.) but no individual rows.
- **Stale fallback:** Catch `InfraError` only (not `Exception`). Log `WARN event=dashboard.stale_fallback` with the error. If no snapshot exists, re-raise.
- **`export_async` threshold:** `BC_ASYNC_EXPORT_THRESHOLD` is a `Settings` field (int). Default per architecture: not specified — subagent MUST add this to `config.py` if not already present.
- **CR-036 — Amount fields as `Decimal`.** Pydantic schema uses `Decimal` type with `model_config = ConfigDict(json_encoders={Decimal: str})`. Never `float`.

---

## 7. Verbatim Outputs

- Empty cycle sentinel: `DashboardResponse(sentinel='尚未開放週期', items=[])`.
- `REPORT_002` — "Report export failed." (raised on export build failure).
- `delta_pct`: String like `'9.1'` or `'N/A'` (never float, never null key).
- `budget_status = 'not_uploaded'` — string (never null or missing key).

---

## 8. Consistency Constraints

**CR-001 — Error code registry single source**
*"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
Codes: `REPORT_002`, `RBAC_001`, `RBAC_002`.

**CR-006 — Audit AFTER commit, BEFORE return**
*"This service commits the DB transaction first, then calls `audit.record(...)`, then returns."*
Applies to: `export_async` sync path (save + audit + return).

**CR-011 — Dashboard scoping uses RBAC.scoped_org_units**
*"This service calls `RBAC.scoped_org_units(user)` and applies the result as a WHERE filter on every query. URL-direct access to org units outside the user's scope returns an empty result set or 403 — never the unfiltered data."*

**CR-013 — Decimal precision (1 decimal place for delta_pct)**
*"`delta_pct` is computed as `Decimal(delta_amount) / Decimal(actual)` then `quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)`. Format as a string (e.g. `'9.1'`) when serializing — never as a float."*

**CR-014 — N/A representation when actual is 0**
*"`delta_pct` is the literal string `'N/A'` when `actual == 0` (or `actual is None`). It is NOT `null`, NOT `0.0`, NOT a missing key."*

**CR-015 — Not-uploaded representation**
*"Rows for org units without a budget upload have `operational_budget: null` AND `budget_status: 'not_uploaded'`. Do not omit the row, do not substitute zero."*

**CR-016 — Three-source reporting threshold: 1000處 and above only**
*"`ConsolidatedReportService.build` populates `personnel_budget` and `shared_cost` only when the row's `org_unit.level_code IN ('1000','0800','0500','0000')`. For 4000/2000 levels (and 6000/5000 if they appear), these fields are `null`."*

**CR-026 — `unsubmitted_for_cycle` shared query**
*"Use `infra.db.repos.budget_uploads_query.unsubmitted_for_cycle(db, cycle_id)` for the unsubmitted-units query. Do not write a new SQL join."*

**CR-033 — Server-side scope filter applied even on list endpoints**
*"List endpoints call `await RBAC.scoped_org_units(user, db)` and pass the resulting set as a WHERE filter on `org_unit_id`."*

**CR-036 — Currency formatting in consolidated report**
*"All `amount` fields in API responses are serialized via `Decimal` with explicit `quantize(Decimal('0.01'))`. Pydantic schema field type is `Decimal`, with `model_config = ConfigDict(json_encoders={Decimal: str})`. Never `float`."*

---

## 9. Tests

### `test_report.py` (unit — delta computation)

1. **`test_delta_pct_one_decimal_round_half_up`** — `delta_amount=100, actual=1100`; assert `delta_pct == '9.1'` (not `'9.09'`, not `9.1` float) (CR-013).
2. **`test_delta_pct_na_when_actual_zero`** — `actual=0, operational_budget=100`; assert `delta_pct == 'N/A'` (CR-014).
3. **`test_budget_status_not_uploaded_when_no_upload`** — org unit with no budget upload; assert row exists, `operational_budget is None`, `budget_status == 'not_uploaded'` (CR-015).
4. **`test_personnel_budget_null_for_4000_level`** — org unit with `level_code='4000'`; assert `personnel_budget is None` and `shared_cost is None` even when personnel data exists (CR-016).
5. **`test_personnel_budget_populated_for_1000_level`** — org unit with `level_code='1000'`, personnel data exists; assert `personnel_budget` is not None (CR-016).

### `test_dashboard.py` (unit)

1. **`test_status_not_downloaded_when_no_download`** — template generated, `download_count=0`; assert status `not_downloaded`.
2. **`test_status_uploaded_when_upload_exists`** — budget upload exists; assert status `uploaded`.
3. **`test_status_resubmit_requested`** — open `ResubmitRequest` exists; assert status `resubmit_requested`.
4. **`test_empty_cycle_returns_sentinel`** — no Open cycle; assert `sentinel == '尚未開放週期'`.
5. **`test_company_reviewer_gets_summary_only`** — `CompanyReviewer` user; assert `items=[]`, `summary` populated.
6. **`test_stale_fallback_on_infra_error`** — DB raises `InfraError`; assert response with `stale=True` from snapshot (if snapshot exists).

### `test_export.py` (integration)

1. **`test_export_sync_returns_201_with_file_url`** — scope <= threshold; assert `ExportEnqueueResult.sync=True`, `file_url` not None, storage file saved.
2. **`test_export_async_returns_202_with_job_id`** — scope > threshold; assert `ExportEnqueueResult.sync=False`, `job_id` not None, job row in DB.
3. **`test_report_export_handler_emails_requester`** — simulate job execution; assert email sent to requester with file URL.

### `test_reports.py` (API)

1. **`test_build_report_requires_authentication`** — unauthenticated GET; assert 401.
2. **`test_build_report_scoped_to_user`** — `UplineReviewer`; assert rows only for their subtree.
3. **`test_export_post_returns_201_or_202`** — `FinanceAdmin` POST export; assert status 201 or 202.
