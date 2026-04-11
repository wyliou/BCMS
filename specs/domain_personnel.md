# Spec: domain/personnel (M5)

**Batch:** 5
**Complexity:** Moderate

## 1. Module Paths & Test Paths

| File | Test |
|---|---|
| `backend/src/app/domain/personnel/service.py` | `backend/tests/unit/personnel/test_service.py`, `backend/tests/integration/personnel/test_service.py` |
| `backend/src/app/domain/personnel/validator.py` | `backend/tests/unit/personnel/test_validator.py` |
| `backend/src/app/domain/personnel/models.py` | n/a |
| `backend/src/app/api/v1/personnel.py` | `backend/tests/api/test_personnel.py` |

---

## 2. Functional Requirements

### FR-024 — Personnel Import Validation (collect-then-report)

- **File formats:** CSV (UTF-8 only) or XLSX. Dispatched via `infra.tabular.parse_table(filename, content)` (CR-024).
- **Column header normalization (CR-019):** Headers normalized via `clean_cell` + `.lower()`, then matched against allow-list:
  `{'dept_id': 'dept_id', '部門id': 'dept_id', 'org_unit_code': 'dept_id', 'account_code': 'account_code', '會科代碼': 'account_code', 'amount': 'amount', '金額': 'amount'}`. Unknown headers → batch-level error before row validation.
- **File size / row count limits (CR-030):** Apply same limits as budget uploads: `BC_MAX_UPLOAD_BYTES` (10 MB) and `BC_MAX_UPLOAD_ROWS` (5000). Reject with batch-level error using `PERS_004` and reason `'file_too_large'` or `'too_many_rows'`.
- **Row-level validation (collect-then-report):**

| # | Check | Error Code | Condition |
|---|---|---|---|
| 1 | `dept_id` exists in org tree | `PERS_001` | `clean_cell(row['dept_id']) not in org_unit_codes` (CR-018) |
| 2 | `account_code` ∈ personnel category | `PERS_002` | `clean_cell(row['account_code']) not in personnel_codes` |
| 3 | `amount` > 0 | `PERS_003` | `parse_amount(value, allow_zero=False)` raises (CR-012, CR-021) |
| 4 | Collect-then-report | `PERS_004` | `BatchValidationError(code='PERS_004', errors=...)` when any row fails |

- **`dept_id` is `org_units.code` (CR-018).** Translate via `org_unit_code_to_id_map(db)`. Unknown codes raise `PERS_001`.
- **`account_code` category check (CR-020).** Use `AccountService.get_codes_by_category(AccountCategory.personnel)` — compare via enum, not string literal.
- **Integral commit (CR-004).** Zero rows persisted on any failure.

### FR-025 — Per-cycle Versioning

- Each successful import creates a new monotonic `version` per `cycle_id` (global, not per org unit — personnel is a company-wide upload, not per-unit).
- `version = await next_version(db, PersonnelBudgetUpload, cycle_id=cycle_id)` (CR-025).
- Snapshot stores: `uploader_id`, `uploaded_at = now_utc()`, `affected_org_units_summary` (JSON: list of `{org_unit_id, total_amount}`), `version`.
- History is read-only; later version supersedes earlier. Audit logged per upload.

### FR-026 — Personnel Import Notification

- **Trigger:** After successful import commit.
- **Recipients:** All users with `FinanceAdmin` role (batch notification).
- **Template:** `NotificationTemplate.personnel_imported` (CR-003).
- **Context:** `{'version': upload.version, 'filename': filename, 'cycle_fiscal_year': cycle.fiscal_year, 'affected_unit_count': len(affected_units)}`.
- **Failure semantics (CR-029).** Notification failure does NOT invalidate import. Catch, mark failed, log WARN, return import.

---

## 3. Exports

```python
# domain/personnel/service.py

async def import_(
    cycle_id: UUID,
    filename: str,
    content: bytes,
    user: User,
) -> PersonnelBudgetUpload:
    """Validate and persist a new personnel budget import version.

    Asserts cycle is Open, validates all rows (collect-then-report), persists
    header + lines transactionally, notifies FinanceAdmin on success.

    Args:
        cycle_id: UUID of the target cycle.
        filename: Original filename (.csv or .xlsx).
        content: Raw file bytes.
        user: Authenticated HRAdmin performing the import.

    Returns:
        PersonnelBudgetUpload: Newly created ORM row with version, snapshot.

    Raises:
        AppError(CYCLE_004): Cycle is not Open.
        BatchValidationError(PERS_004): One or more row errors; nothing persisted.
    """

async def list_versions(cycle_id: UUID) -> list[PersonnelBudgetUpload]:
    """Return all personnel import versions for a cycle, ordered by version asc.

    Args:
        cycle_id: UUID of the cycle.

    Returns:
        list[PersonnelBudgetUpload]: All versions (read-only history).
    """

async def get(upload_id: UUID) -> PersonnelBudgetUpload:
    """Fetch a single personnel import by UUID.

    Args:
        upload_id: UUID of the personnel import.

    Returns:
        PersonnelBudgetUpload: ORM row.

    Raises:
        NotFoundError: Import does not exist.
    """

async def get_latest_by_cycle(
    cycle_id: UUID,
) -> dict[tuple[UUID, UUID], Decimal]:
    """Return a map of (org_unit_id, account_code_id) -> amount from latest version.

    Used by ConsolidatedReportService (M7) to join personnel amounts.

    Args:
        cycle_id: UUID of the cycle.

    Returns:
        dict[tuple[UUID, UUID], Decimal]: Personnel amounts from highest version.
    """

# domain/personnel/validator.py

def validate(
    rows: list[dict],
    *,
    org_unit_codes: dict[str, UUID],
    personnel_codes: set[str],
) -> ValidationResult:
    """Validate rows from a parsed personnel import file.

    Checks dept_id in org tree (PERS_001), account_code in personnel category
    (PERS_002), amount > 0 (PERS_003). Collects all RowErrors.

    Args:
        rows: Parsed rows from infra.tabular.parse_table.
        org_unit_codes: Map of org_unit.code -> UUID from org_unit_code_to_id_map.
        personnel_codes: Set of account codes in AccountCategory.personnel.

    Returns:
        ValidationResult: .valid is True only if errors list is empty.
    """
```

---

## 4. Imports

| Module | Symbols | Called by |
|---|---|---|
| `domain.cycles` | `CycleService.assert_open` | `import_` — first action (CR-005) |
| `domain.accounts` | `AccountService.get_codes_by_category`, `AccountCategory` | `import_` — get personnel codes |
| `domain.notifications` | `NotificationService.send_batch`, `NotificationTemplate` | `import_` — notify FinanceAdmins (CR-029) |
| `domain.audit` | `AuditService.record`, `AuditAction` | After commit in `import_` |
| `core.security` | `User`, `Role`, `RBAC` | Route RBAC enforcement |
| `domain._shared.row_validation` | `RowError`, `ValidationResult`, `clean_cell`, `parse_amount`, `AmountParseError` | `PersonnelImportValidator.validate` |
| `domain._shared.queries` | `org_unit_code_to_id_map` | `import_` — translate dept_id to UUID (CR-018) |
| `infra.tabular` | `parse_table` | `import_` — CSV/XLSX dispatch (CR-024) |
| `infra.storage` | `save` | `import_` — store raw file |
| `infra.db` | `get_session`, `AsyncSession` | All service methods |
| `infra.db.helpers` | `next_version` | `import_` — monotonic version (CR-025) |
| `core.errors` | `AppError`, `BatchValidationError`, `NotFoundError` | Error raising |
| `core.clock` | `now_utc` | `uploaded_at` timestamp |

### Required Call Order in `PersonnelImportService.import_` (CR-004, CR-005, CR-006)

1. **`await cycles.assert_open(cycle_id)`** — raises `CYCLE_004`. **First action.** (CR-005)
2. File size check: `if len(content) > settings.bc_max_upload_bytes: raise BatchValidationError(code='PERS_004', errors=[...reason='file_too_large'])` (CR-030).
3. `rows = await infra.tabular.parse_table(filename, content)` — dispatch by extension (CR-024).
4. Header normalization (CR-019): check required columns present; raise batch-level if missing.
5. Row count check: `if len(rows) > settings.bc_max_upload_rows: raise BatchValidationError(code='PERS_004', ...)` (CR-030).
6. `org_unit_codes = await org_unit_code_to_id_map(db)` — single query (CR-018).
7. `personnel_codes = await account_service.get_codes_by_category(AccountCategory.personnel)` (CR-020).
8. `result = PersonnelImportValidator.validate(rows, org_unit_codes=org_unit_codes, personnel_codes=personnel_codes)` — full row validation (CR-004).
9. If `not result.valid`: raise `BatchValidationError(code='PERS_004', errors=result.errors)`. **Zero rows persisted.**
10. Compute `affected_org_units_summary` from validated rows.
11. `storage_key = await infra.storage.save(category='personnel', filename=filename, content=content)`.
12. Open persisting transaction:
    - `version = await next_version(db, PersonnelBudgetUpload, cycle_id=cycle_id)` (CR-025).
    - `INSERT PersonnelBudgetUpload` header.
    - `INSERT PersonnelBudgetLine` rows.
13. `await db.commit()`.
14. `await audit.record(AuditAction.PERSONNEL_IMPORT, ...)` (CR-006).
15. Send notification (separate try/except — CR-029).
16. Return `PersonnelBudgetUpload`.

---

## 5. Side Effects

- Creates `personnel_budget_uploads` and `personnel_budget_lines` rows on success.
- Saves raw file bytes to `infra.storage`.
- Sends `personnel_imported` notification to FinanceAdmins (may fail silently per CR-029).
- Writes `audit_logs` row after commit.

---

## 6. Gotchas

- **CR-012 — `allow_zero=False` for personnel.** `parse_amount(value, allow_zero=False)` — amount must be strictly > 0. Do NOT copy `allow_zero=True` from budget uploads.
- **CR-018 — `dept_id` is org_unit code, not UUID.** Translate via `org_unit_code_to_id_map`. A UUID-format `dept_id` that is not in the map raises `PERS_001` (not a SQL error).
- **CR-019 — Header normalization.** Normalize before row iteration. Unknown headers = batch error.
- **CR-020 — `AccountCategory.personnel` enum member**, not string `'personnel'`.
- **CR-021 — Wrap `parse_amount` in try/except AmountParseError.** Caught → `RowError(code='PERS_003')`.
- **CR-024 — Use `infra.tabular.parse_table`**, not `infra.csv_io` or `infra.excel` directly.
- **CR-025 — `next_version` per `cycle_id`** (not per org unit — personnel is per-cycle global version).
- **CR-029 — Notification failure does not invalidate.** Wrap notification call in `try/except`.
- **CR-030 — Apply same 10 MB / 5000-row limits.** PRD does not specify limits for personnel; apply the same as budget uploads.
- **`affected_org_units_summary`:** Compute before insert as `[{'org_unit_id': str(uid), 'total_amount': str(total)} for uid, total in grouped.items()]`. Stored as JSONB.

---

## 7. Verbatim Outputs

- `PERS_001` — `RowError(column='dept_id', code='PERS_001', reason='Unknown dept_id: <value>')`.
- `PERS_002` — `RowError(column='account_code', code='PERS_002', reason='Account code is not in personnel category')`.
- `PERS_003` — `RowError(column='amount', code='PERS_003', reason=str(AmountParseError))` or `'Amount must be > 0'`.
- `PERS_004` — `BatchValidationError(code='PERS_004')` when any row fails or file size/count exceeded.

---

## 8. Consistency Constraints

**CR-001 — Error code registry single source**
*"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
Codes: `PERS_001`, `PERS_002`, `PERS_003`, `PERS_004`, `CYCLE_004`.

**CR-004 — Validation BEFORE persistence (collect-then-report)**
*"This service performs validation entirely before opening the persisting transaction. On any `RowError`, raise `BatchValidationError` and persist zero rows."*

**CR-005 — Cycle state assertion BEFORE write operations**
*"This service's first action is `await cycles.assert_open(cycle_id)`. Subsequent steps may assume the cycle is Open."*

**CR-006 — Audit AFTER commit, BEFORE return**
*"This service commits the DB transaction first, then calls `audit.record(...)`, then returns. If audit fails, the entire operation is rolled back."*

**CR-012 — Personnel/shared_cost amount > 0; Budget amount ≥ 0**
*"This module calls `parse_amount(value, allow_zero=False)` for personnel (FR-024)."*

**CR-018 — `dept_id` column is org_unit code, not UUID**
*"The `dept_id` column from the CSV is treated as `org_units.code`. Translate via `org_unit_code_to_id_map(db)` from `domain/_shared/queries`. Unknown codes raise `PERS_001` with a row-level error."*

**CR-019 — Excel column header casing for importers**
*"The importer normalizes incoming column headers via `clean_cell` + `.lower()` then matches against an allow-list. Unknown headers raise a single batch-level error before row validation begins."*

**CR-020 — Account-category lookup is exact-match on enum value**
*"All category comparisons use the `AccountCategory` enum members directly (`AccountCategory.personnel` etc.); no string literals."*

**CR-021 — Robust amount parsing wrapped in try/except**
*"Every call to `parse_amount` is wrapped in `try/except AmountParseError`, and the caught exception becomes a `RowError(row=..., column='amount', code='PERS_003', reason=str(e))`."*

**CR-024 — File extension dispatch lives in `infra/tabular` only**
*"File parsing is delegated to `infra.tabular.parse_table(filename, content)`. Do not import `infra.csv_io` or `infra.excel` directly from a domain importer."*

**CR-025 — `next_version` shared helper**
*"`version = await next_version(db, ModelName, **filters)` is called inside the same transaction as the upload-row insert."*

**CR-029 — Notification failure does NOT invalidate upload**
*"The upload service commits in transaction T1, then calls `notifications.send` separately. If `send` raises, catch, mark failed, log WARN, return the successful upload."*

**CR-030 — Personnel/shared_cost batch size limit**
*"Apply the same `BC_MAX_UPLOAD_BYTES` (10 MB) and `BC_MAX_UPLOAD_ROWS` (5000) limits. Reject with `PERS_004` carrying reason 'file_too_large' or 'too_many_rows'."*

---

## 9. Tests

### `test_validator.py` (unit — one test per error code)

1. **`test_validate_pers_001_unknown_dept_id`** — `dept_id='9999'` not in `org_unit_codes`; assert `RowError(column='dept_id', code='PERS_001')` at correct row.
2. **`test_validate_pers_002_wrong_account_category`** — `account_code='OP001'` (operational, not personnel); assert `RowError(column='account_code', code='PERS_002')`.
3. **`test_validate_pers_003_non_numeric_amount`** — `amount='abc'`; `AmountParseError` caught; assert `RowError(column='amount', code='PERS_003')`.
4. **`test_validate_pers_003_zero_amount_rejected`** — `amount=0` with `allow_zero=False`; assert `RowError(column='amount', code='PERS_003', reason contains '> 0')` (CR-012).
5. **`test_validate_all_valid_rows`** — 3 valid rows; assert `ValidationResult.valid == True`.

### `test_service.py` (integration)

1. **`test_import_success_creates_version_1`** — valid CSV, Open cycle; assert `PersonnelBudgetUpload.version=1`, lines in DB, FinanceAdmin notification sent, audit entry.
2. **`test_import_second_version_increments`** — two successful imports same cycle; second has `version=2`.
3. **`test_import_cycle_closed_raises_cycle_004`** — Closed cycle; assert `CYCLE_004` before file parsing.
4. **`test_import_invalid_row_zero_persisted`** — row with unknown `dept_id`; assert `BatchValidationError(PERS_004)`; DB unchanged.
5. **`test_import_notification_failure_does_not_invalidate`** — SMTP raises; assert import row exists (CR-029).

### `test_personnel.py` (API)

1. **`test_import_requires_hr_admin`** — POST as `FilingUnitManager`; assert 403.
2. **`test_import_valid_csv_returns_201`** — POST valid CSV as `HRAdmin`; assert 201.
3. **`test_import_invalid_rows_returns_400`** — POST bad CSV; assert 400, `error.code == 'PERS_004'`, row-level details.
4. **`test_list_versions_requires_authentication`** — unauthenticated GET; assert 401.
