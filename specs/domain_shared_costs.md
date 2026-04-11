# Spec: domain/shared_costs (M6)

**Batch:** 5
**Complexity:** Moderate

## 1. Module Paths & Test Paths

| File | Test |
|---|---|
| `backend/src/app/domain/shared_costs/service.py` | `backend/tests/unit/shared_costs/test_service.py`, `backend/tests/integration/shared_costs/test_service.py` |
| `backend/src/app/domain/shared_costs/validator.py` | `backend/tests/unit/shared_costs/test_validator.py` |
| `backend/src/app/domain/shared_costs/models.py` | n/a |
| `backend/src/app/api/v1/shared_costs.py` | `backend/tests/api/test_shared_costs.py` |

---

## 2. Functional Requirements

### FR-027 — Shared Cost Import Validation (collect-then-report)

- **File formats:** CSV (UTF-8 only) or XLSX. Dispatched via `infra.tabular.parse_table(filename, content)` (CR-024).
- **Column header normalization (CR-019):** Same allow-list as personnel:
  `{'dept_id': 'dept_id', '部門id': 'dept_id', 'org_unit_code': 'dept_id', 'account_code': 'account_code', '會科代碼': 'account_code', 'amount': 'amount', '金額': 'amount'}`. Unknown headers → batch-level error.
- **File size / row count limits (CR-030):** `BC_MAX_UPLOAD_BYTES` (10 MB) and `BC_MAX_UPLOAD_ROWS` (5000). Reject with `SHARED_004` and reason `'file_too_large'` or `'too_many_rows'`.
- **Row-level validation (collect-then-report):**

| # | Check | Error Code | Condition |
|---|---|---|---|
| 1 | `dept_id` exists in org tree | `SHARED_001` | `clean_cell(row['dept_id']) not in org_unit_codes` (CR-018) |
| 2 | `account_code` ∈ shared_cost category | `SHARED_002` | `clean_cell(row['account_code']) not in shared_cost_codes` |
| 3 | `amount` > 0 | `SHARED_003` | `parse_amount(value, allow_zero=False)` raises (CR-012, CR-021) |
| 4 | Collect-then-report | `SHARED_004` | `BatchValidationError(code='SHARED_004', errors=...)` when any row fails |

- **`dept_id` is `org_units.code` (CR-018).** Translate via `org_unit_code_to_id_map(db)`.
- **`account_code` category check (CR-020).** Use `AccountService.get_codes_by_category(AccountCategory.shared_cost)`.
- **Integral commit (CR-004).** Zero rows persisted on any failure.

### FR-028 — Per-cycle Versioning with Per-org-unit Amount Diff Summary

- Each successful import creates a new monotonic `version` per `cycle_id` (global, not per org unit).
- `version = await next_version(db, SharedCostUpload, cycle_id=cycle_id)` (CR-025).
- Snapshot stores: `uploader_id`, `uploaded_at = now_utc()`, `affected_org_units_summary` (JSON including per-org-unit `{org_unit_id, prev_amount, new_amount, delta}` — showing diff from previous version), `version`.
- History is read-only. Audit logged per upload.

### FR-029 — Shared Cost Import Notification with Diff

- **Trigger:** After successful import commit.
- **Diff computation:** `diff_affected_units(prev_lines, new_lines) -> list[UUID]` computes the symmetric diff of org units between the previous version's lines and the new version's lines. An org unit is "affected" if:
  - Its total amount changed between versions (any delta).
  - It appears in new version but not previous (new department).
  - It appears in previous but not in new (removed department).
- **Recipients:** Manager of each affected org unit (one notification per unit manager, resolved by walking `parent_id` for the manager user, CR-028). If a unit has no manager, log WARN and skip (do not raise).
- **Template:** `NotificationTemplate.shared_cost_imported` (CR-003).
- **Context:** `{'version': upload.version, 'org_unit_name': ou.name, 'prev_amount': str(prev), 'new_amount': str(new), 'delta': str(delta), 'cycle_fiscal_year': cycle.fiscal_year}`.
- **Failure semantics (CR-029).** Notification failure does NOT invalidate import. Catch, mark failed, log WARN, continue.
- **First-version case:** If no previous version exists, all org units in the new import are considered "affected" (new entrants).

---

## 3. Exports

```python
# domain/shared_costs/service.py

async def import_(
    cycle_id: UUID,
    filename: str,
    content: bytes,
    user: User,
) -> SharedCostUpload:
    """Validate and persist a new shared cost import version.

    Asserts cycle is Open, validates all rows (collect-then-report), persists
    header + lines transactionally, computes diff with previous version, and
    notifies affected department managers.

    Args:
        cycle_id: UUID of the target cycle.
        filename: Original filename (.csv or .xlsx).
        content: Raw file bytes.
        user: Authenticated FinanceAdmin performing the import.

    Returns:
        SharedCostUpload: Newly created ORM row with version, diff summary.

    Raises:
        AppError(CYCLE_004): Cycle is not Open.
        BatchValidationError(SHARED_004): One or more row errors; nothing persisted.
    """

async def list_versions(cycle_id: UUID) -> list[SharedCostUpload]:
    """Return all shared cost import versions for a cycle, ordered by version asc.

    Args:
        cycle_id: UUID of the cycle.

    Returns:
        list[SharedCostUpload]: All versions (read-only history).
    """

async def get(upload_id: UUID) -> SharedCostUpload:
    """Fetch a single shared cost import by UUID.

    Args:
        upload_id: UUID of the shared cost upload.

    Returns:
        SharedCostUpload: ORM row.

    Raises:
        NotFoundError: Import does not exist.
    """

async def get_latest_by_cycle(
    cycle_id: UUID,
) -> dict[tuple[UUID, UUID], Decimal]:
    """Return a map of (org_unit_id, account_code_id) -> amount from latest version.

    Used by ConsolidatedReportService (M7) to join shared cost amounts.

    Args:
        cycle_id: UUID of the cycle.

    Returns:
        dict[tuple[UUID, UUID], Decimal]: Shared cost amounts from highest version.
    """

def diff_affected_units(
    prev_lines: list[SharedCostLine],
    new_lines: list[SharedCostLine],
) -> list[UUID]:
    """Compute org unit IDs affected by a shared cost version change.

    An org unit is affected if: its aggregate amount changed, it is new in the
    new version, or it was present in the previous but absent in the new.
    Symmetric diff semantics: any non-zero change counts.

    Args:
        prev_lines: SharedCostLine rows from the previous version (may be empty).
        new_lines: SharedCostLine rows from the new version.

    Returns:
        list[UUID]: Unique org_unit_ids that are affected.
    """

# domain/shared_costs/validator.py

def validate(
    rows: list[dict],
    *,
    org_unit_codes: dict[str, UUID],
    shared_cost_codes: set[str],
) -> ValidationResult:
    """Validate rows from a parsed shared cost import file.

    Checks dept_id in org tree (SHARED_001), account_code in shared_cost
    category (SHARED_002), amount > 0 (SHARED_003). Collects all RowErrors.

    Args:
        rows: Parsed rows from infra.tabular.parse_table.
        org_unit_codes: Map of org_unit.code -> UUID from org_unit_code_to_id_map.
        shared_cost_codes: Set of account codes in AccountCategory.shared_cost.

    Returns:
        ValidationResult: .valid is True only if errors list is empty.
    """
```

---

## 4. Imports

| Module | Symbols | Called by |
|---|---|---|
| `domain.cycles` | `CycleService.assert_open` | `import_` — first action (CR-005) |
| `domain.accounts` | `AccountService.get_codes_by_category`, `AccountCategory` | `import_` — get shared_cost codes |
| `domain.notifications` | `NotificationService.send`, `NotificationTemplate` | `import_` — per-unit diff notifications (CR-029) |
| `domain.audit` | `AuditService.record`, `AuditAction` | After commit in `import_` |
| `core.security` | `User`, `Role`, `RBAC` | Route RBAC enforcement |
| `domain._shared.row_validation` | `RowError`, `ValidationResult`, `clean_cell`, `parse_amount`, `AmountParseError` | `SharedCostImportValidator.validate` |
| `domain._shared.queries` | `org_unit_code_to_id_map` | `import_` — translate dept_id (CR-018) |
| `infra.tabular` | `parse_table` | `import_` — CSV/XLSX dispatch (CR-024) |
| `infra.storage` | `save` | `import_` — store raw file |
| `infra.db` | `get_session`, `AsyncSession` | All service methods |
| `infra.db.helpers` | `next_version` | `import_` — monotonic version (CR-025) |
| `core.errors` | `AppError`, `BatchValidationError`, `NotFoundError` | Error raising |
| `core.clock` | `now_utc` | `uploaded_at` timestamp |

### Required Call Order in `SharedCostImportService.import_` (CR-004, CR-005, CR-006)

1. **`await cycles.assert_open(cycle_id)`** — raises `CYCLE_004`. **First action.** (CR-005)
2. File size check: `if len(content) > settings.bc_max_upload_bytes: raise BatchValidationError(code='SHARED_004', ...)` (CR-030).
3. `rows = await infra.tabular.parse_table(filename, content)` (CR-024).
4. Header normalization (CR-019): check required columns; raise batch-level if missing.
5. Row count check: `if len(rows) > settings.bc_max_upload_rows: raise BatchValidationError(code='SHARED_004', ...)` (CR-030).
6. `org_unit_codes = await org_unit_code_to_id_map(db)` (CR-018).
7. `shared_cost_codes = await account_service.get_codes_by_category(AccountCategory.shared_cost)` (CR-020).
8. `result = SharedCostImportValidator.validate(rows, org_unit_codes=..., shared_cost_codes=...)` (CR-004).
9. If `not result.valid`: raise `BatchValidationError(code='SHARED_004', errors=result.errors)`. **Zero rows persisted.**
10. Fetch previous version lines (for diff): `prev_upload = await get_latest(cycle_id)` → `prev_lines = prev_upload.lines if prev_upload else []`.
11. Compute `affected_unit_ids = diff_affected_units(prev_lines, new_lines_from_result)`.
12. Compute `affected_org_units_summary` with prev/new/delta per unit.
13. `storage_key = await infra.storage.save(category='shared_costs', filename=filename, content=content)`.
14. Open persisting transaction:
    - `version = await next_version(db, SharedCostUpload, cycle_id=cycle_id)` (CR-025).
    - `INSERT SharedCostUpload` header.
    - `INSERT SharedCostLine` rows.
15. `await db.commit()`.
16. `await audit.record(AuditAction.SHARED_COST_IMPORT, ...)` (CR-006).
17. Send per-affected-unit notifications (separate try/except per unit — CR-029):
    ```python
    for org_unit_id in affected_unit_ids:
        try:
            manager_id = await _resolve_manager(org_unit_id, db)
            if manager_id:
                await notification_service.send(NotificationTemplate.shared_cost_imported, ...)
            else:
                log.warn("shared_cost.no_manager_found", org_unit_id=org_unit_id)
        except AppError:
            log.warn("shared_cost.notification_failed", org_unit_id=org_unit_id)
    ```
18. Return `SharedCostUpload`.

---

## 5. Side Effects

- Creates `shared_cost_uploads` and `shared_cost_lines` rows on success.
- Saves raw file bytes to `infra.storage`.
- Sends `shared_cost_imported` notifications to affected department managers (may fail silently per CR-029).
- Writes `audit_logs` row after commit.

---

## 6. Gotchas

- **CR-012 — `allow_zero=False` for shared costs.** `parse_amount(value, allow_zero=False)`. Amount must be > 0.
- **CR-018 — `dept_id` is org_unit code.** Translate via `org_unit_code_to_id_map`.
- **CR-019 — Header normalization.** Same allow-list as personnel.
- **CR-020 — `AccountCategory.shared_cost` enum member**, not string `'shared_cost'`.
- **CR-021 — Wrap `parse_amount` in try/except.** → `RowError(code='SHARED_003')`.
- **CR-024 — Use `infra.tabular.parse_table`.** Do not import `infra.csv_io` or `infra.excel`.
- **CR-025 — `next_version` per `cycle_id`** (global per cycle).
- **CR-029 — Notification failure does not invalidate.** Per-unit notification wrapped in `try/except`.
- **CR-030 — 10 MB / 5000-row limits.**
- **`diff_affected_units` is a pure function:** It takes two lists of ORM rows and returns a list of UUIDs. No DB calls. It is called AFTER the new lines are prepared (from `result.rows`) and BEFORE the persisting transaction. This means it works on Python objects, not committed DB rows.
- **Diff symmetric semantics:** Compare `{org_unit_id: total_amount}` dicts for prev and new. Affected = any unit where `prev.get(uid) != new.get(uid)` (including `None` vs value in either direction).
- **First-version case:** When `prev_lines = []`, all org units in new version are affected.
- **`get_latest` is used before commit for diff:** This reads the DB for the current max-version row. This is safe because it is a read before the new transaction opens.

---

## 7. Verbatim Outputs

- `SHARED_001` — `RowError(column='dept_id', code='SHARED_001', reason='Unknown dept_id: <value>')`.
- `SHARED_002` — `RowError(column='account_code', code='SHARED_002', reason='Account code is not in shared_cost category')`.
- `SHARED_003` — `RowError(column='amount', code='SHARED_003', reason=str(AmountParseError))` or `'Amount must be > 0'`.
- `SHARED_004` — `BatchValidationError(code='SHARED_004')` when any row fails or file limits exceeded.

---

## 8. Consistency Constraints

**CR-001 — Error code registry single source**
*"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
Codes: `SHARED_001`, `SHARED_002`, `SHARED_003`, `SHARED_004`, `CYCLE_004`.

**CR-004 — Validation BEFORE persistence (collect-then-report)**
*"This service performs validation entirely before opening the persisting transaction. On any `RowError`, raise `BatchValidationError` and persist zero rows."*

**CR-005 — Cycle state assertion BEFORE write operations**
*"This service's first action is `await cycles.assert_open(cycle_id)`. Subsequent steps may assume the cycle is Open."*

**CR-006 — Audit AFTER commit, BEFORE return**
*"This service commits the DB transaction first, then calls `audit.record(...)`, then returns."*

**CR-012 — Personnel/shared_cost amount > 0; Budget amount ≥ 0**
*"This module calls `parse_amount(value, allow_zero=False)` for shared_cost (FR-027)."*

**CR-018 — `dept_id` column is org_unit code, not UUID**
*"The `dept_id` column from the CSV is treated as `org_units.code`. Translate via `org_unit_code_to_id_map(db)`. Unknown codes raise `SHARED_001` with a row-level error."*

**CR-019 — Excel column header casing for importers**
*"The importer normalizes incoming column headers via `clean_cell` + `.lower()` then matches against an allow-list. Unknown headers raise a single batch-level error before row validation begins."*

**CR-020 — Account-category lookup is exact-match on enum value**
*"All category comparisons use the `AccountCategory` enum members directly; no string literals."*

**CR-021 — Robust amount parsing wrapped in try/except**
*"Every call to `parse_amount` is wrapped in `try/except AmountParseError`, and the caught exception becomes a `RowError(row=..., column='amount', code='SHARED_003', reason=str(e))`."*

**CR-024 — File extension dispatch lives in `infra/tabular` only**
*"File parsing is delegated to `infra.tabular.parse_table(filename, content)`."*

**CR-025 — `next_version` shared helper**
*"`version = await next_version(db, ModelName, **filters)` is called inside the same transaction as the upload-row insert."*

**CR-029 — Notification failure does NOT invalidate upload**
*"The upload service commits in T1, then calls `notifications.send` separately. If `send` raises, catch, mark failed, log WARN, return successful upload."*

**CR-030 — Personnel/shared_cost batch size limit**
*"Apply the same `BC_MAX_UPLOAD_BYTES` (10 MB) and `BC_MAX_UPLOAD_ROWS` (5000) limits. Reject with `SHARED_004` carrying reason 'file_too_large' or 'too_many_rows'."*

---

## 9. Tests

### `test_validator.py` (unit — one test per error code)

1. **`test_validate_shared_001_unknown_dept_id`** — `dept_id='9999'` not in `org_unit_codes`; assert `RowError(column='dept_id', code='SHARED_001')` at correct row.
2. **`test_validate_shared_002_wrong_account_category`** — `account_code='OP001'` (operational); assert `RowError(column='account_code', code='SHARED_002')`.
3. **`test_validate_shared_003_non_numeric_amount`** — `amount='abc'`; `AmountParseError` caught; assert `RowError(column='amount', code='SHARED_003')`.
4. **`test_validate_shared_003_zero_amount_rejected`** — `amount=0` with `allow_zero=False`; assert `RowError(column='amount', code='SHARED_003', reason contains '> 0')` (CR-012).
5. **`test_validate_all_valid_rows`** — 3 valid rows; assert `ValidationResult.valid == True`.

### `test_service.py` — `diff_affected_units` (unit)

1. **`test_diff_new_department_is_affected`** — prev has unit A; new has unit A + unit B; assert B in result.
2. **`test_diff_removed_department_is_affected`** — prev has units A+B; new has only A; assert B in result.
3. **`test_diff_changed_amount_is_affected`** — prev A=100; new A=200; assert A in result.
4. **`test_diff_unchanged_not_included`** — prev A=100; new A=100; assert A NOT in result.
5. **`test_diff_empty_prev_all_new_affected`** — prev=[]; new has A,B; assert [A, B] in result.

### `test_service.py` (integration)

1. **`test_import_success_creates_version_1`** — valid CSV, Open cycle; assert `SharedCostUpload.version=1`, lines in DB, audit entry.
2. **`test_import_second_version_sends_diff_notifications`** — version 1 has org unit A=100; version 2 has A=200; assert notification sent to A's manager.
3. **`test_import_cycle_closed_raises_cycle_004`** — Closed cycle; assert `CYCLE_004` before parsing.
4. **`test_import_invalid_row_zero_persisted`** — row with unknown `dept_id`; assert `BatchValidationError(SHARED_004)`; DB unchanged.

### `test_shared_costs.py` (API)

1. **`test_import_requires_finance_admin`** — POST as `HRAdmin`; assert 403.
2. **`test_import_valid_csv_returns_201`** — POST valid CSV as `FinanceAdmin`; assert 201.
3. **`test_import_invalid_rows_returns_400`** — POST bad CSV; assert 400, `error.code == 'SHARED_004'`.
4. **`test_list_versions_requires_authentication`** — unauthenticated GET; assert 401.
