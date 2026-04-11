# BCMS Consistency Registry

Cross-cutting constraints discovered by scanning PRD v4.3 (and architecture.md where it operationalizes a PRD rule). Every entry has a verbatim "Stage B check" line that spec writers must paste into the affected module specs, and a "Final-gate check" describing the grep/inspection step the build pipeline runs before declaring a batch done.

---

### CR-001 — Error code registry single source

- **Category:** ownership_uniqueness
- **Concern:** Every error code (`AUTH_001`..`SYS_003`, ~38 codes) must be defined in exactly one place. Multiple FRs reference the same code (e.g. `CYCLE_004` raised from FR-006 but checked by FR-011/024/027), so independent modules must NOT each define their own.
- **Affected modules:** `core/errors`, every `domain/*`, `api/v1/*` (global exception handler)
- **Owner:** `app/core/errors.py` `ERROR_REGISTRY`
- **Stage B check:** *"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
- **Final-gate check:** Grep `raise.*Error\(["']([A-Z]+_\d{3})["']` across `backend/src/app/`, collect codes, diff against `ERROR_REGISTRY` keys; fail if any code is raised but not registered, OR raised in two different modules without going through `core.errors`.

### CR-002 — Audit action enum single source

- **Category:** ownership_uniqueness
- **Concern:** Auditable actions (`LOGIN_SUCCESS`, `BUDGET_UPLOAD`, `PERSONNEL_IMPORT`, `SHARED_COST_IMPORT`, `RESUBMIT_REQUEST`, `CYCLE_OPEN`, `CYCLE_CLOSE`, `RBAC_DENIED`, etc.) are emitted by many modules but must be a single closed enum so the audit query (`?action=`) is reliable.
- **Affected modules:** `domain/audit`, all callers
- **Owner:** `app/domain/audit/actions.py` `AuditAction` StrEnum
- **Stage B check:** *"All `audit.record(...)` calls in this module use a member of `app.domain.audit.actions.AuditAction`; no string literals."*
- **Final-gate check:** Grep `audit.record\(\s*["']` (string-literal first arg) — must be empty.

### CR-003 — Notification template names single source

- **Category:** ownership_uniqueness
- **Concern:** Template strings (`"cycle_opened"`, `"upload_confirmed"`, `"resubmit_requested"`, `"deadline_reminder"`, `"personnel_imported"`, `"shared_cost_imported"`) are referenced by 5+ caller modules and must match a fixed set of files in `domain/notifications/templates/`.
- **Affected modules:** `domain/notifications`, `domain/cycles`, `domain/budget_uploads`, `domain/personnel`, `domain/shared_costs`
- **Owner:** `app/domain/notifications/templates.py` `NotificationTemplate` StrEnum + `templates/` directory
- **Stage B check:** *"All `notifications.send/send_batch` calls pass a member of `NotificationTemplate`; no string literals."*
- **Final-gate check:** Grep `\.send(_batch)?\(\s*["']` against `notifications` callers — must be empty. Cross-check that every `NotificationTemplate` member has a matching `*.txt` template file.

### CR-004 — Validation BEFORE persistence (collect-then-report)

- **Category:** sequencing_dependency
- **Concern:** FR-008/011/024/027 all require "整批驗證通過才寫入" — entire-file validation must happen before any DB write. A subagent might inline a per-row insert + try/except, leaving partial state on failure.
- **Affected modules:** `domain/accounts` (actuals), `domain/budget_uploads`, `domain/personnel`, `domain/shared_costs`
- **Stage B check:** *"This service performs validation entirely before opening the persisting transaction. On any `RowError`, raise `BatchValidationError` and persist zero rows. The persisting transaction wraps `INSERT upload header + INSERT lines` only — never INSERT-then-validate."*
- **Final-gate check:** Inspect each importer service for the call order: `validator.validate(...)` MUST come before any `db.add` / `INSERT`. CI test: import a 3-row file where row 2 is invalid; assert that DB row count is unchanged.

### CR-005 — Cycle state assertion BEFORE write operations

- **Category:** sequencing_dependency
- **Concern:** FR-006 says all writes (budget upload, personnel import, shared cost import) raise `CYCLE_004` if cycle is Closed. This check must happen at the START of every write service, before any other validation, file I/O, or DB work.
- **Affected modules:** M4 budget_uploads, M5 personnel, M6 shared_costs, M2 accounts (actuals import)
- **Stage B check:** *"This service's first action is `await cycles.assert_open(cycle_id)`. Subsequent steps may assume the cycle is Open."*
- **Final-gate check:** Static inspection of each importer service: `assert_open` call must precede file parsing.

### CR-006 — Audit AFTER commit, BEFORE return

- **Category:** sequencing_dependency
- **Concern:** FR-023 requires every state-changing action to be audited, but if audit is recorded inside the same transaction as the operation it could be silently lost on rollback; if recorded before commit it could record a non-event.
- **Affected modules:** every `domain/*` service that mutates state
- **Stage B check:** *"This service commits the DB transaction first, then calls `audit.record(...)`, then returns. If audit fails, the entire operation is rolled back (audit failure = cannot honor FR-023)."*
- **Final-gate check:** Code review heuristic — `audit.record` calls in services should follow `await db.commit()` (or be inside a context manager that commits then audits). Not enforceable by grep alone; require unit test that simulates `audit.record` raising and verifies the calling service raises and rolls back.

### CR-007 — Resubmit record BEFORE notification send (FR-019)

- **Category:** sequencing_dependency
- **Concern:** FR-019 explicitly forbids "已發送但未紀錄" — record must be written before email is sent. If write fails, raise `NOTIFY_002` and DO NOT send the email.
- **Affected modules:** `domain/notifications.ResubmitRequestService`
- **Stage B check:** *"`ResubmitRequestService.create` writes the resubmit_requests row in a transaction; only after successful commit does it call `NotificationService.send`. Row-write failure raises `NOTIFY_002` and no email goes out."*
- **Final-gate check:** Unit test that injects a DB failure on `resubmit_requests` insert and asserts (a) `NOTIFY_002` is raised, (b) `email.send` was NOT called.

### CR-008 — Filing-unit list resolution before manager check (FR-002)

- **Category:** sequencing_dependency
- **Concern:** FR-002 requires the system to enumerate filing units (4000 to 0500 inclusive), THEN check each one has a manager. A naive implementation might check `User.org_unit_id` references and miss filing units that have no User row at all (the missing-manager case).
- **Affected modules:** `domain/cycles.filing_units`
- **Stage B check:** *"`list_filing_units(cycle_id)` first enumerates ALL `org_units WHERE is_filing_unit = TRUE`, then LEFT JOINs to users to compute `has_manager`. The check returns `has_manager=False` rows so the caller can warn — it does NOT silently filter them out."*
- **Final-gate check:** Test fixture with one filing unit that has zero User rows pointing to it; assert `list_filing_units` returns it with `has_manager: False`, and `cycles.open()` raises `CYCLE_002`.

### CR-009 — Operational-only template generation (FR-009)

- **Category:** representation_variant
- **Concern:** FR-009 explicitly says template "不含人力預算與公攤費用欄位". The template builder must filter `account_codes` by `category = 'operational'` only. A subagent might iterate all categories.
- **Affected modules:** `domain/templates.builder`
- **Stage B check:** *"The template builder pulls account codes via `accounts.get_operational_codes_set()` (or `get_codes_by_category('operational')`); personnel and shared_cost categories are NEVER written to the workbook."*
- **Final-gate check:** Generate a template in test, parse it back, assert no row references a personnel or shared_cost category code.

### CR-010 — 0000公司 excluded from filing-unit operations (FR-002, FR-003, FR-009)

- **Category:** representation_variant
- **Concern:** 0000公司 has `is_reviewer_only = TRUE` and is NEVER a filing unit. PRD repeats this in §1.2, FR-002, FR-003, FR-009. A subagent reading only one FR could miss the rule and include 0000 in template generation or notification dispatch.
- **Affected modules:** M1 cycles (filing unit list, reminder dispatch), M3 templates (generation), M8 notifications (cycle_opened batch)
- **Stage B check:** *"This module never treats `org_units WHERE level_code = '0000'` as a filing unit. Use the `is_filing_unit = TRUE` filter consistently — do NOT filter by level_code."*
- **Final-gate check:** Grep `level_code\s*==?\s*['"]0000['"]` across `backend/src/app/domain/`; matches should be limited to RBAC scoping (CompanyReviewer role) and consolidation report routing — never in template/notification dispatch logic.

### CR-011 — Dashboard scoping uses RBAC.scoped_org_units (FR-014, FR-022)

- **Category:** detection_with_fallback
- **Concern:** Dashboard and consolidated report MUST filter by the requesting user's scoped org units. A direct URL to a higher-level cycle MUST be blocked server-side, not by hiding the link in the frontend (FR-022 explicit).
- **Affected modules:** M7 consolidation (dashboard + report), M4 budget_uploads list, M3 templates download
- **Stage B check:** *"This service calls `RBAC.scoped_org_units(user)` and applies the result as a WHERE filter on every query. URL-direct access to org units outside the user's scope returns an empty result set or 403 — never the unfiltered data."*
- **Final-gate check:** Test matrix: every (role × resource) pair from PRD §5. Each pair must either return scoped data or 403 — never 200 with out-of-scope rows.

### CR-012 — Personnel/shared_cost amount > 0; Budget amount ≥ 0

- **Category:** shared_convention
- **Concern:** FR-024 and FR-027 require positive amounts (`amount > 0`); FR-011 requires non-negative (`amount >= 0`). The shared `parse_amount` helper takes `allow_zero` to encode this. A subagent might invert the rule or copy-paste the wrong value.
- **Affected modules:** M4 budget_uploads (`allow_zero=True`), M5 personnel (`allow_zero=False`), M6 shared_costs (`allow_zero=False`)
- **Owner:** `app/domain/_shared/row_validation.parse_amount`
- **Stage B check:** *"This module calls `parse_amount(value, allow_zero=True)` for budget uploads (FR-011), `allow_zero=False` for personnel (FR-024) and shared_cost (FR-027). The DB CHECK constraints (`amount >= 0` for `budget_lines`, `amount > 0` for `personnel_budget_lines` and `shared_cost_lines`) are the second line of defense."*
- **Final-gate check:** Grep `parse_amount\(.*allow_zero` and confirm: budget_uploads → `True`, personnel → `False`, shared_costs → `False`. CI test: zero amount accepted by budget, rejected by personnel and shared_cost.

### CR-013 — Decimal precision (1 decimal place for delta_pct)

- **Category:** shared_convention
- **Concern:** FR-016 specifies "百分比, 1 位小數" — one decimal place. A subagent might use Python `round()` (banker's rounding) or write `:.2f`.
- **Affected modules:** M7 consolidation (report.py)
- **Stage B check:** *"`delta_pct` is computed as `Decimal(delta_amount) / Decimal(actual)` then `quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)`. Format as a string (e.g. `'9.1'`) when serializing — never as a float."*
- **Final-gate check:** Unit test asserting that `delta_amount=100, actual=1100` produces `delta_pct == "9.1"` (not `"9.09"`, not `9.1` float).

### CR-014 — N/A representation when actual is 0 (FR-016)

- **Category:** representation_variant
- **Concern:** FR-016 explicit boundary: "實際費用為 0 時比率欄顯示『N/A』而非除以零錯誤". A subagent might raise `ZeroDivisionError` or return `null`.
- **Affected modules:** M7 consolidation
- **Stage B check:** *"`delta_pct` is the literal string `'N/A'` when `actual == 0` (or `actual is None`). It is NOT `null`, NOT `0.0`, NOT a missing key."*
- **Final-gate check:** Unit test asserting `actual=0, budget=100` → row contains `"delta_pct": "N/A"`.

### CR-015 — Not-uploaded representation (FR-016)

- **Category:** representation_variant
- **Concern:** FR-016 says budget column for not-yet-uploaded units shows "未上傳". Architecture §5.9 maps this to `budget_status: "not_uploaded"`. The numeric `operational_budget` field remains `null`.
- **Affected modules:** M7 consolidation
- **Stage B check:** *"Rows for org units without a budget upload have `operational_budget: null` AND `budget_status: 'not_uploaded'`. Do not omit the row, do not substitute zero."*
- **Final-gate check:** Unit test with one filing unit that has not uploaded; assert row exists, `operational_budget is None`, `budget_status == "not_uploaded"`.

### CR-016 — Three-source reporting threshold: 1000處 and above only (FR-015)

- **Category:** representation_variant
- **Concern:** FR-015 + PRD §8.3 explicit: personnel_budget and shared_cost columns appear ONLY for org units at level 1000處 or higher (1000, 0800, 0500, 0000). For lower levels, those two columns are `null`. A subagent might populate them for every row.
- **Affected modules:** M7 consolidation (report.py)
- **Stage B check:** *"`ConsolidatedReportService.build` populates `personnel_budget` and `shared_cost` only when the row's `org_unit.level_code IN ('1000','0800','0500','0000')`. For 4000/2000 levels (and 6000/5000 if they appear), these fields are `null`."*
- **Final-gate check:** Unit test with mixed-level org tree; assert 4000 rows have `personnel_budget is None` and 1000 rows have a value (or `None` if no personnel data exists).

### CR-017 — Filing-unit lookup by `is_filing_unit` flag, NOT by `level_code` set

- **Category:** representation_variant
- **Concern:** Filing units are 4000–0500 *by rule* but the schema has an explicit `is_filing_unit BOOLEAN`. Some FRs ("4000部至 0500 BG") tempt a literal `level_code IN (...)` query. The intent is that org admins can override via the boolean.
- **Affected modules:** M1 cycles, M3 templates, M8 notifications, M7 consolidation
- **Stage B check:** *"All filing-unit queries use `WHERE is_filing_unit = TRUE`. The `level_code` is informational and may not always match the rule — `is_filing_unit` is the source of truth."*
- **Final-gate check:** Grep `level_code\s+IN` across `backend/src/app/`; allowed only inside `domain/cycles/filing_units.py` (the place that enforces the default rule when seeding) and in RBAC role mapping. Never inside importer services or report builders.

### CR-018 — `dept_id` column is org_unit code, not UUID (FR-024, FR-027)

- **Category:** representation_variant
- **Concern:** PRD says "部門ID" in the CSV/Excel for personnel and shared_cost imports. This is the human-readable `org_units.code` (e.g. "4023"), not the internal UUID. Subagents might assume UUID and fail to translate.
- **Affected modules:** M5 personnel, M6 shared_costs, `domain/_shared/queries`
- **Stage B check:** *"The `dept_id` column from the CSV is treated as `org_units.code`. Translate via `org_unit_code_to_id_map(db)` from `domain/_shared/queries`. Unknown codes raise `PERS_001` / `SHARED_001` with a row-level error."*
- **Final-gate check:** Test CSV with a UUID in `dept_id`; assert `PERS_001` (not a SQL error).

### CR-019 — Excel column header casing for importers

- **Category:** identifier_casing
- **Concern:** CSV headers are user-supplied and may vary (`dept_id` vs `Dept_ID` vs `部門ID`). Architecture's contract is `dept_id, account_code, amount` but real-world Excel files may use Chinese headers.
- **Affected modules:** M5 personnel, M6 shared_costs
- **Stage B check:** *"The importer normalizes incoming column headers via `clean_cell` + `.lower()` then matches against an allow-list `{'dept_id': 'dept_id', '部門id': 'dept_id', 'org_unit_code': 'dept_id', 'account_code': 'account_code', '會科代碼': 'account_code', 'amount': 'amount', '金額': 'amount'}`. Unknown headers raise a single batch-level error before row validation begins."*
- **Final-gate check:** Test CSV with mixed-case English and Traditional Chinese headers; assert successful import.

### CR-020 — Account-category lookup is exact-match on enum value

- **Category:** identifier_casing
- **Concern:** `AccountCategory` enum members are `operational`, `personnel`, `shared_cost`. Subagents might compare against `'Personnel'` or `'PERSONNEL'`.
- **Affected modules:** M2 accounts, M5 personnel, M6 shared_costs, M3 templates
- **Stage B check:** *"All category comparisons use the `AccountCategory` enum members directly (`AccountCategory.personnel` etc.); no string literals. SQL queries pass the enum value to SQLAlchemy's enum binding."*
- **Final-gate check:** Grep `['"](operational|personnel|shared_cost)['"]` across `backend/src/app/domain/`; matches should be inside `app/domain/accounts/models.py` enum definition only.

### CR-021 — Robust amount parsing wrapped in try/except

- **Category:** input_robustness
- **Concern:** `parse_amount` raises `AmountParseError` (a `ValueError` subclass) on bad input. Importers must catch this per row and translate to a `RowError` — they MUST NOT let it propagate as an unhandled exception.
- **Affected modules:** M2 accounts (actuals), M4 budget_uploads, M5 personnel, M6 shared_costs
- **Stage B check:** *"Every call to `parse_amount` is wrapped in `try/except AmountParseError`, and the caught exception becomes a `RowError(row=..., column='amount', code='UPLOAD_005|PERS_003|SHARED_003|ACCOUNT_002', reason=str(e))`."*
- **Final-gate check:** Unit test with non-numeric amount cell; assert `BatchValidationError` with the right code, not `AmountParseError` propagating to the API.

### CR-022 — `clean_cell` for every user-supplied string field

- **Category:** input_robustness
- **Concern:** Excel/CSV cells may be `None`, `int` (when openpyxl reads numeric headers), `str` with whitespace, or `str` with Excel's invisible BOM. `clean_cell` normalizes all of these to `str | None`.
- **Affected modules:** all importers (M2, M4, M5, M6)
- **Stage B check:** *"Every cell read from openpyxl or `csv.DictReader` is passed through `clean_cell` before comparison. Direct `==` comparisons on raw cell values are forbidden."*
- **Final-gate check:** Grep for `\.cell\([^)]*\)\.value\s*==` against `backend/src/app/domain/` — must be empty (use `clean_cell(...)` first).

### CR-023 — Currency code accepted but not converted (PRD §2.3)

- **Category:** input_robustness
- **Concern:** `BudgetCycle.reporting_currency` is stored but multi-currency is out of scope. A subagent might attempt FX conversion. The field is informational only.
- **Affected modules:** M1 cycles, M7 consolidation, M2 accounts
- **Stage B check:** *"`reporting_currency` is validated as a 3-letter ISO 4217 code on cycle create and stored as-is. NO conversion logic anywhere — sums use the raw amounts. Default `'TWD'`."*
- **Final-gate check:** Grep `convert\|exchange\|fx_rate\|currency_rate` across `backend/src/app/domain/`; must be empty.

### CR-024 — File extension dispatch lives in `infra/tabular` only

- **Category:** ownership_uniqueness
- **Concern:** Three importers (M2 actuals, M5 personnel, M6 shared_costs) accept both CSV and Excel. The dispatch (`.csv` → csv parser; `.xlsx` → openpyxl) MUST live in one place — `infra/tabular.parse_table` — to avoid drift.
- **Affected modules:** M2 actuals, M5 personnel, M6 shared_costs
- **Owner:** `app/infra/tabular.py`
- **Stage B check:** *"File parsing is delegated to `infra.tabular.parse_table(filename, content)`. Do not import `infra.csv_io` or `infra.excel` directly from a domain importer."*
- **Final-gate check:** Grep `from app\.infra\.(csv_io|excel)` inside `backend/src/app/domain/{accounts,personnel,shared_costs}/`; allowed only in M3 templates (which generates Excel directly).

### CR-025 — `next_version` shared helper

- **Category:** ownership_uniqueness
- **Concern:** FR-012, FR-025, FR-028 all describe per-cycle/(per-org-unit) monotonic versioning. Three importers must use the same race-safe implementation.
- **Affected modules:** M4 budget_uploads, M5 personnel, M6 shared_costs
- **Owner:** `app/infra/db/helpers.next_version`
- **Stage B check:** *"`version = await next_version(db, ModelName, **filters)` is called inside the same transaction as the upload-row insert. The UNIQUE constraint on `(cycle_id, org_unit_id, version)` (or `(cycle_id, version)`) is the safety net for concurrent uploads."*
- **Final-gate check:** Grep `MAX\(version\)` across `backend/src/app/domain/`; must be empty (only `infra/db/helpers.py` is allowed). Concurrency test: launch two simultaneous uploads for the same `(cycle, org_unit)`; assert one succeeds with v1, the other retries to v2.

### CR-026 — `unsubmitted_for_cycle` shared query

- **Category:** ownership_uniqueness
- **Concern:** Both `cycles.dispatch_deadline_reminders` (FR-005/020) and `consolidation.dashboard` (FR-014) need "filing units that have not uploaded yet for cycle". Two separate implementations would drift.
- **Affected modules:** M1 cycles, M7 consolidation
- **Owner:** `app/infra/db/repos/budget_uploads_query.unsubmitted_for_cycle`
- **Stage B check:** *"Use `infra.db.repos.budget_uploads_query.unsubmitted_for_cycle(db, cycle_id)` for the unsubmitted-units query. Do not write a new SQL join."*
- **Final-gate check:** Grep `LEFT (OUTER )?JOIN.*budget_uploads` across `backend/src/app/domain/`; allowed only in `infra/db/repos/budget_uploads_query.py` and `domain/consolidation/report.py` (which performs the three-source join).

### CR-027 — `unsubmitted` excludes already-uploaded units (FR-005)

- **Category:** detection_with_fallback
- **Concern:** FR-005 explicit: "已上傳單位自動排除". The shared query must NOT return units that have at least one upload.
- **Affected modules:** `infra/db/repos/budget_uploads_query`
- **Stage B check:** *"`unsubmitted_for_cycle` returns filing units (`is_filing_unit = TRUE`) for the cycle that have ZERO rows in `budget_uploads` for that `(cycle_id, org_unit_id)`. Test with a unit that has 2 upload versions; the unit is NOT in the result set."*
- **Final-gate check:** Unit test with three units: A (0 uploads), B (1 upload), C (2 uploads). Assert result = [A] only.

### CR-028 — Email recipient computation: filing-unit manager + upline reviewer (FR-013, FR-020)

- **Category:** detection_with_fallback
- **Concern:** FR-013 says notify uploader and "其直屬上階主管". FR-020 says recipients include "副本其直屬上階主管". The "upline reviewer" computation walks the org tree until it hits a node where some user holds an upline reviewer role. If no manager is found, the recipient list must NOT silently shrink — the dispatch must log a WARN and continue.
- **Affected modules:** M1 cycles, M4 budget_uploads, M8 notifications
- **Stage B check:** *"The recipient resolver walks `parent_id` from the source org unit until it finds an `OrgUnit` with at least one User holding `UplineReviewer` (or the FinanceAdmin role for global recipients). If no upline is found at the top of the tree, log `event=notification.no_upline_found` at WARN with the source org unit id; do not raise."*
- **Final-gate check:** Unit test with an org unit whose entire chain has no users; assert the upload succeeds, the email is sent to the uploader, and a WARN log entry is emitted.

### CR-029 — Notification failure does NOT invalidate upload (FR-013)

- **Category:** detection_with_fallback
- **Concern:** FR-013 explicit: "通知發送失敗 ... 不影響上傳本身的有效性". A subagent might wrap the upload + notification in one transaction and rollback the upload on SMTP failure.
- **Affected modules:** M4 budget_uploads, M5 personnel, M6 shared_costs
- **Stage B check:** *"The upload service commits the upload in transaction T1, then calls `notifications.send` in a separate transaction. If `send` raises (SMTP down, etc.), catch the `NOTIFY_001` exception, mark the notification row `failed`, log WARN, and return the successful `BudgetUpload` to the caller. The upload remains valid."*
- **Final-gate check:** Test simulating SMTP failure on upload-confirmation; assert the upload row exists and the response is 201, with the notification row marked `failed`.

### CR-030 — Personnel/shared_cost batch size limit not specified

- **Category:** input_robustness
- **Concern:** FR-011 sets 10 MB / 5000 rows for budget Excel. FR-024/027 do NOT set a limit. Subagents might forget to validate batch size and accept arbitrarily large CSVs that OOM the worker.
- **Affected modules:** M5 personnel, M6 shared_costs
- **Stage B check:** *"Apply the same `BC_MAX_UPLOAD_BYTES` (10 MB) and `BC_MAX_UPLOAD_ROWS` (5000) limits to personnel and shared_cost imports. Reject oversize files with a batch-level `PERS_004` / `SHARED_004` carrying a `'file_too_large'` reason — same envelope shape as row-level errors."*
- **Final-gate check:** Test with an 11 MB CSV; assert rejected. Test with 5001 rows; assert rejected.

### CR-031 — Hash chain payload format

- **Category:** shared_convention
- **Concern:** Hash chain verification in `audit.verify_chain` must replay exactly the same byte serialization that `record` used. Any drift (key ordering, datetime format, JSON spacing) breaks the chain.
- **Affected modules:** M9 audit
- **Owner:** `app/domain/audit/service.py` (single private `_serialize_for_chain` function)
- **Stage B check:** *"Audit row payload is serialized via the single private `_serialize_for_chain(row) -> bytes` helper. JSON keys sorted, separators `(',', ':')`, datetimes as ISO-8601 with UTC `+00:00`. `verify_chain` uses the same helper. NEVER duplicate the serialization logic."*
- **Final-gate check:** Test that records 100 entries, then calls `verify_chain` against the same range and asserts `verified=True`. Tamper one row's `details` field and assert `AUDIT_001` is raised.

### CR-032 — RBAC scope matrix completeness

- **Category:** ownership_uniqueness
- **Concern:** PRD §5 defines 7 roles with specific permissions. The RBAC test matrix must enumerate every (role × resource) pair so a missing check is impossible.
- **Affected modules:** M10 core/security (rbac), every `api/v1/*` route handler
- **Stage B check:** *"This route declares `Depends(RBAC.require_role(...))` AND, where the URL contains a resource id, `Depends(RBAC.require_scope(resource_type, resource_id_param))`. Both must be present — `require_role` alone is insufficient for scoped resources."*
- **Final-gate check:** A `tests/api/test_rbac_matrix.py` file iterating every (role, route) pair from PRD §5 + architecture §5.* and asserting either 200/201/202 or 403 — never 200 with out-of-scope data and never 401 (unauth is a separate concern).

### CR-033 — Server-side scope filter applied even on list endpoints

- **Category:** detection_with_fallback
- **Concern:** Even endpoints without an `{org_unit_id}` path param (e.g. `GET /budget-uploads?cycle_id=...`) MUST filter results by `RBAC.scoped_org_units`. The architecture explicitly says "前端隱藏入口" is not sufficient.
- **Affected modules:** M4, M5, M6 list endpoints; M7 dashboard + report; M9 audit list
- **Stage B check:** *"List endpoints call `await RBAC.scoped_org_units(user, db)` and pass the resulting set as a WHERE filter on `org_unit_id`. The query is run once per request; no caching across users."*
- **Final-gate check:** API test: as a 4000-level filing unit manager, list `/api/v1/cycles/{id}/org-units/{other_org}/budget-uploads` — must be 403 OR an empty list (depending on the route's design).

### CR-034 — `actual_expenses` zero-row template generation (FR-009)

- **Category:** detection_with_fallback
- **Concern:** FR-009 boundary: "若填報單位在當年度無任何實績費用,樣板仍產生,實績欄顯示 0". A subagent might skip template generation when the actuals query returns empty.
- **Affected modules:** M3 templates
- **Stage B check:** *"`generate_for_cycle` produces a template even when `actual_expenses` is empty for the (cycle, org_unit). Empty rows display `0`, and the full operational account list is still rendered."*
- **Final-gate check:** Unit test: cycle with one filing unit and zero `actual_expenses` rows; assert template is generated, file_path exists, and parsing the file shows operational account rows with `0` actuals.

### CR-035 — Cron callback exception isolation

- **Category:** detection_with_fallback
- **Concern:** APScheduler will keep running if a single callback raises, but the failure must be logged + the next-run state must be preserved. A subagent might let the exception propagate and silently kill the scheduler thread.
- **Affected modules:** M1 cycles (reminders), `infra/scheduler`
- **Stage B check:** *"The cron callback wraps its body in `try/except Exception` at the outermost layer. On exception: `log.error('scheduler.callback_failed', ...)` and return — never re-raise."*
- **Final-gate check:** Test: register a callback that raises; assert the scheduler is still running and the next run executes.

### CR-036 — Currency formatting in consolidated report (FR-015)

- **Category:** shared_convention
- **Concern:** Numeric amounts in the report response must be JSON-serialized as `Decimal` → string OR int (cents); never float (loses precision). The frontend may then format for display.
- **Affected modules:** M7 consolidation, M4–M6 export
- **Stage B check:** *"All `amount` fields in API responses are serialized via `Decimal` with explicit `quantize(Decimal('0.01'))`. Pydantic schema field type is `Decimal`, with `model_config = ConfigDict(json_encoders={Decimal: str})` (or equivalent v2 serializer). Never `float`."*
- **Final-gate check:** Grep `: float` and `Float\(` across `backend/src/app/schemas/` and `backend/src/app/domain/*/models.py`; allowed only for `delta_pct` if explicitly typed as `Decimal` (preferred) — flag any `float` for review.

### CR-037 — Reopen window enforcement (FR-006)

- **Category:** sequencing_dependency
- **Concern:** FR-006 allows reopen within `BC_REOPEN_WINDOW_DAYS` after `closed_at`. A subagent might check `created_at` or `updated_at` instead.
- **Affected modules:** M1 cycles
- **Stage B check:** *"`reopen()` raises `CYCLE_005` if `(now_utc() - cycle.closed_at).days > BC_REOPEN_WINDOW_DAYS`. The check uses `closed_at` specifically — not `created_at` or `updated_at`."*
- **Final-gate check:** Unit test: cycle closed 8 days ago with `BC_REOPEN_WINDOW_DAYS=7`; assert `CYCLE_005`. Closed 6 days ago; assert reopen succeeds.

### CR-038 — Time zone for cron evaluation (FR-005)

- **Category:** shared_convention
- **Concern:** FR-005 says "每日 09:00（伺服器時區）". The architecture sets `BC_TIMEZONE=Asia/Taipei`. APScheduler must be configured with this TZ explicitly — its default is UTC, which would shift the trigger by 8 hours.
- **Affected modules:** `infra/scheduler`, M1 cycles
- **Stage B check:** *"`infra.scheduler` configures APScheduler with `timezone=ZoneInfo(settings.timezone)`. The cron expression `0 9 * * *` is interpreted as 09:00 in Asia/Taipei, NOT UTC."*
- **Final-gate check:** Unit test: with `BC_TIMEZONE=Asia/Taipei`, the next run computed for `0 9 * * *` after `2026-04-12T00:00:00+08:00` is `2026-04-12T09:00:00+08:00` (`2026-04-12T01:00:00Z`).
