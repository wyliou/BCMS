# Spec: domain/budget_uploads (M4)

**Batch:** 5
**Complexity:** Complex

## 1. Module Paths & Test Paths

| File | Test |
|---|---|
| `backend/src/app/domain/budget_uploads/service.py` | `backend/tests/unit/budget_uploads/test_service.py`, `backend/tests/integration/budget_uploads/test_service.py` |
| `backend/src/app/domain/budget_uploads/validator.py` | `backend/tests/unit/budget_uploads/test_validator.py` |
| `backend/src/app/domain/budget_uploads/models.py` | n/a |
| `backend/src/app/api/v1/budget_uploads.py` | `backend/tests/api/test_budget_uploads.py` |

---

## 2. Functional Requirements

### FR-011 — Budget Upload Validation Chain (collect-then-report)

The validation chain is applied in this enumerated order. All checks are collected before reporting (CR-004).

| # | Check | Error Code | Condition |
|---|---|---|---|
| 1 | File size ≤ 10 MB (CR-010) | `UPLOAD_001` | `len(content) > BC_MAX_UPLOAD_BYTES` — batch-level, raised before parsing |
| 2 | Row count ≤ 5000 | `UPLOAD_002` | `len(rows) > BC_MAX_UPLOAD_ROWS` — batch-level after parsing |
| 3 | Dept code matches assigned org unit | `UPLOAD_003` | Cell `dept_code` in workbook != `expected_dept_code` for this org unit |
| 4 | Required cells non-empty | `UPLOAD_004` | `account_code` or `dept_code` cell is `None` or empty after `clean_cell` |
| 5 | Amount format valid (numeric) | `UPLOAD_005` | `parse_amount` raises `AmountParseError` (CR-021) |
| 6 | Amount ≥ 0 | `UPLOAD_006` | `parse_amount(value, allow_zero=True)` — zero is valid (CR-012) |
| 7 | Collect-then-report summary | `UPLOAD_007` | If any row errors exist, raise `BatchValidationError(code='UPLOAD_007', errors=...)` |

- **File format:** `.xlsx` only (budget upload is Excel only, per PRD §4.3).
- **Parsing:** `infra.excel.read_rows(workbook)` used directly (not `infra.tabular`) since budget uploads are Excel-only and the workbook is already open.
- **`parse_amount` call:** `parse_amount(cell_value, allow_zero=True)` (CR-012).
- **Integral commit (CR-004):** Zero rows persisted on any row-level error.

### FR-012 — Version Chain

- Each successful upload creates a new monotonic `version` integer per `(cycle_id, org_unit_id)`.
- `version = await next_version(db, BudgetUpload, cycle_id=cycle_id, org_unit_id=org_unit_id)` (CR-025). Called inside the same transaction as the insert.
- Stores: `uploader_id`, `uploaded_at = now_utc()`, `file_hash` (SHA-256 of content bytes), `filename`, `version`.
- Latest version is the effective version. All versions are retained as read-only history (≥5 years).
- `get_latest(cycle_id, org_unit_id)` returns the row with the highest `version` for that pair, or `None`.

### FR-013 — Upload Confirmation Notification

- **Trigger:** After successful upload commit.
- **Recipients:** Uploader (`user.id`) AND direct upline manager (resolved by `NotificationService._resolve_upline_manager`).
- **Template:** `NotificationTemplate.upload_confirmed` (CR-003).
- **Context:** `{'version': upload.version, 'filename': upload.filename, 'org_unit_name': org_unit.name, 'cycle_fiscal_year': cycle.fiscal_year}`.
- **Failure semantics (CR-029):** Notification failure does NOT invalidate the upload. Catch `NOTIFY_001`, mark notification `failed`, log WARN, return upload.

---

## 3. Exports

```python
# domain/budget_uploads/service.py

async def upload(
    cycle_id: UUID,
    org_unit_id: UUID,
    filename: str,
    content: bytes,
    user: User,
) -> BudgetUpload:
    """Validate and persist a new budget upload version.

    Asserts cycle is Open, validates the workbook (size, rows, dept code,
    required cells, amounts), persists the upload and lines, sends confirmation
    notification. Integral commit: zero rows on any validation failure.

    Args:
        cycle_id: UUID of the target cycle.
        org_unit_id: UUID of the uploading org unit.
        filename: Original filename (must end in .xlsx).
        content: Raw workbook bytes.
        user: Authenticated user performing the upload (FilingUnitManager).

    Returns:
        BudgetUpload: Newly created ORM row with version, file_hash, etc.

    Raises:
        AppError(CYCLE_004): Cycle is not Open.
        BatchValidationError(UPLOAD_007): One or more validation errors; nothing persisted.
    """

async def list_versions(
    cycle_id: UUID,
    org_unit_id: UUID,
) -> list[BudgetUpload]:
    """Return all upload versions for a (cycle, org_unit) pair, ordered by version asc.

    Args:
        cycle_id: UUID of the cycle.
        org_unit_id: UUID of the org unit.

    Returns:
        list[BudgetUpload]: All versions (read-only history).
    """

async def get(upload_id: UUID) -> BudgetUpload:
    """Fetch a single upload by UUID.

    Args:
        upload_id: UUID of the upload.

    Returns:
        BudgetUpload: ORM row.

    Raises:
        NotFoundError: Upload does not exist.
    """

async def get_latest(
    cycle_id: UUID,
    org_unit_id: UUID,
) -> BudgetUpload | None:
    """Return the latest (highest version) upload for a (cycle, org_unit) pair.

    Args:
        cycle_id: UUID of the cycle.
        org_unit_id: UUID of the org unit.

    Returns:
        BudgetUpload | None: Latest upload, or None if none exists.
    """

async def get_latest_by_cycle(
    cycle_id: UUID,
) -> dict[tuple[UUID, UUID], Decimal]:
    """Return a map of (org_unit_id, account_code_id) -> total amount for a cycle.

    Used by ConsolidatedReportService (M7) to join budget amounts into the report.

    Args:
        cycle_id: UUID of the cycle.

    Returns:
        dict[tuple[UUID, UUID], Decimal]: Map for the latest upload version per org unit.
    """

# domain/budget_uploads/validator.py

def validate(
    workbook: object,
    *,
    expected_dept_code: str,
    operational_codes: set[str],
) -> ValidationResult:
    """Validate a budget upload workbook.

    Checks: dept code match (UPLOAD_003), required cells (UPLOAD_004),
    amount format (UPLOAD_005), amount >= 0 (UPLOAD_006). Collects all
    RowErrors before returning. Row count check (UPLOAD_002) is done
    in the service before calling this validator.

    Args:
        workbook: openpyxl Workbook object (already opened).
        expected_dept_code: The org unit's code; must match workbook dept cell.
        operational_codes: Set of valid account code strings.

    Returns:
        ValidationResult: .valid is True only if errors list is empty.
    """
```

---

## 4. Imports

| Module | Symbols | Called by |
|---|---|---|
| `domain.cycles` | `CycleService.assert_open` | `upload` — first action (CR-005) |
| `domain.accounts` | `AccountService.get_operational_codes_set` | `upload` — pass to validator |
| `domain.notifications` | `NotificationService.send`, `NotificationTemplate` | `upload` — post-commit notification (CR-029) |
| `domain.audit` | `AuditService.record`, `AuditAction` | After commit in `upload` |
| `core.security` | `User`, `Role`, `RBAC` | Route RBAC enforcement; `scoped_org_units` in list endpoint |
| `domain._shared.row_validation` | `RowError`, `ValidationResult`, `clean_cell`, `parse_amount`, `AmountParseError` | `BudgetUploadValidator.validate` |
| `infra.excel` | `open_workbook`, `read_rows` | `upload` — parse workbook; budget uploads are Excel-only |
| `infra.storage` | `save` | `upload` — store raw file bytes |
| `infra.db` | `get_session`, `AsyncSession` | All service methods |
| `infra.db.helpers` | `next_version` | `upload` — monotonic version (CR-025) |
| `core.errors` | `AppError`, `BatchValidationError`, `NotFoundError` | Error raising |
| `core.clock` | `now_utc` | `uploaded_at` timestamp |

### Required Call Order in `BudgetUploadService.upload` (CR-004, CR-005, CR-006)

1. **`await cycles.assert_open(cycle_id)`** — raises `CYCLE_004` if not Open. **This is the first call.** (CR-005)
2. File size check: `if len(content) > settings.bc_max_upload_bytes: raise AppError(code='UPLOAD_001')`.
3. `workbook = infra.excel.open_workbook(content)` — parse bytes.
4. `rows = infra.excel.read_rows(workbook)` — read rows.
5. Row count check: `if len(rows) > settings.bc_max_upload_rows: raise AppError(code='UPLOAD_002')`.
6. `operational_codes = await account_service.get_operational_codes_set()`.
7. `result = BudgetUploadValidator.validate(workbook, expected_dept_code=..., operational_codes=operational_codes)` — full validation (CR-004).
8. If `not result.valid`: raise `BatchValidationError(code='UPLOAD_007', errors=result.errors)`. **Zero rows persisted.**
9. `file_hash = hashlib.sha256(content).hexdigest()`.
10. `storage_key = await infra.storage.save(category='budget_uploads', filename=filename, content=content)`.
11. Open persisting transaction:
    - `version = await next_version(db, BudgetUpload, cycle_id=cycle_id, org_unit_id=org_unit_id)` (CR-025).
    - `INSERT BudgetUpload` header row.
    - `INSERT BudgetLine` rows.
12. `await db.commit()`.
13. `await audit.record(AuditAction.BUDGET_UPLOAD, ...)` (CR-006).
14. Send notification (separate try/except for CR-029):
    ```python
    try:
        await notification_service.send(
            NotificationTemplate.upload_confirmed,
            recipient_ids=[user.id, upline_manager_id],
            context={...},
        )
    except AppError:
        log.warn("budget_upload.notification_failed", ...)
    ```
15. Return `BudgetUpload`.

**Rationale:** Step 1 is CR-005. Steps 7–8 fully precede step 11 (CR-004). Step 12 precedes step 13 (CR-006). Step 14 is outside the DB transaction (CR-029).

---

## 5. Side Effects

- Creates `budget_uploads` and `budget_lines` rows on successful upload.
- Saves raw `.xlsx` bytes to `infra.storage`.
- Sends `upload_confirmed` notification email (may fail silently per CR-029).
- Writes `audit_logs` row after commit.

---

## 6. Gotchas

- **CR-012 — `allow_zero=True` for amounts (CR-012).** Budget lines may be zero (`amount >= 0`). Do NOT copy `allow_zero=False` from personnel/shared_costs.
- **CR-021 — Wrap `parse_amount` in try/except AmountParseError.** Each cell call: `try: parse_amount(v, allow_zero=True) except AmountParseError as e: errors.append(RowError(..., code='UPLOAD_005', reason=str(e)))`.
- **CR-022 — `clean_cell` every cell.** `dept_code` and `account_code` cells must pass through `clean_cell` before comparison.
- **CR-025 — `next_version` inside transaction.** The UNIQUE constraint `(cycle_id, org_unit_id, version)` handles concurrent uploads — retry on conflict.
- **CR-029 — Notification failure does NOT invalidate upload.** The notification call is outside the upload transaction and wrapped in `try/except`.
- **UPLOAD_001/002 are batch-level errors** (not row-level `RowError`). They are raised as `AppError` (not `BatchValidationError`) and short-circuit before row validation begins.
- **File format is `.xlsx` only** for budget uploads. Reject `.csv` with `AppError(code='UPLOAD_001', message='Only .xlsx files are accepted')` (or a dedicated code — use whichever is in `ERROR_REGISTRY`).
- **`get_latest_by_cycle` aggregation:** Returns amounts from `BudgetLine` rows associated with the max-version `BudgetUpload` per `org_unit_id`. SQL must use a subquery/CTE for the max version — not a Python-level filter on all rows.
- **CR-033 — Server-side scope filter on list endpoints.** `list_versions` and `get_latest` endpoints call `RBAC.scoped_org_units(user, db)` and filter by `org_unit_id IN scoped_set`.

---

## 7. Verbatim Outputs

- `UPLOAD_001` — file size / format error (batch-level).
- `UPLOAD_002` — row count exceeds limit (batch-level).
- `UPLOAD_003` — `RowError(column='dept_code', code='UPLOAD_003', reason='Dept code does not match assigned org unit')`.
- `UPLOAD_004` — `RowError(column=<col>, code='UPLOAD_004', reason='Required cell is empty')`.
- `UPLOAD_005` — `RowError(column='amount', code='UPLOAD_005', reason=str(AmountParseError))`.
- `UPLOAD_006` — `RowError(column='amount', code='UPLOAD_006', reason='Amount must be >= 0')` — note: with `allow_zero=True`, `parse_amount` already handles this; validator collects the RowError.
- `UPLOAD_007` — `BatchValidationError(code='UPLOAD_007')` raised when `not result.valid`.

---

## 8. Consistency Constraints

**CR-001 — Error code registry single source**
*"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
Codes: `UPLOAD_001`, `UPLOAD_002`, `UPLOAD_003`, `UPLOAD_004`, `UPLOAD_005`, `UPLOAD_006`, `UPLOAD_007`, `CYCLE_004`.

**CR-004 — Validation BEFORE persistence (collect-then-report)**
*"This service performs validation entirely before opening the persisting transaction. On any `RowError`, raise `BatchValidationError` and persist zero rows. The persisting transaction wraps `INSERT upload header + INSERT lines` only — never INSERT-then-validate."*

**CR-005 — Cycle state assertion BEFORE write operations**
*"This service's first action is `await cycles.assert_open(cycle_id)`. Subsequent steps may assume the cycle is Open."*

**CR-006 — Audit AFTER commit, BEFORE return**
*"This service commits the DB transaction first, then calls `audit.record(...)`, then returns. If audit fails, the entire operation is rolled back (audit failure = cannot honor FR-023)."*

**CR-012 — Personnel/shared_cost amount > 0; Budget amount ≥ 0**
*"This module calls `parse_amount(value, allow_zero=True)` for budget uploads (FR-011)."*

**CR-021 — Robust amount parsing wrapped in try/except**
*"Every call to `parse_amount` is wrapped in `try/except AmountParseError`, and the caught exception becomes a `RowError(row=..., column='amount', code='UPLOAD_005', reason=str(e))`."*

**CR-022 — `clean_cell` for every user-supplied string field**
*"Every cell read from openpyxl or `csv.DictReader` is passed through `clean_cell` before comparison."*

**CR-025 — `next_version` shared helper**
*"`version = await next_version(db, ModelName, **filters)` is called inside the same transaction as the upload-row insert. The UNIQUE constraint on `(cycle_id, org_unit_id, version)` is the safety net for concurrent uploads."*

**CR-029 — Notification failure does NOT invalidate upload**
*"The upload service commits the upload in transaction T1, then calls `notifications.send` in a separate transaction. If `send` raises, catch the `NOTIFY_001` exception, mark the notification row `failed`, log WARN, and return the successful `BudgetUpload` to the caller."*

**CR-033 — Server-side scope filter applied even on list endpoints**
*"List endpoints call `await RBAC.scoped_org_units(user, db)` and pass the resulting set as a WHERE filter on `org_unit_id`."*

---

## 9. Tests

### `test_validator.py` (unit — one test per error code)

1. **`test_validate_upload_003_dept_code_mismatch`** — workbook dept cell = `'4099'`, `expected_dept_code='4023'`; assert `RowError(column='dept_code', code='UPLOAD_003')` at row 1 with correct row number.
2. **`test_validate_upload_004_empty_account_code`** — row with `account_code` cell empty after `clean_cell`; assert `RowError(column='account_code', code='UPLOAD_004')`.
3. **`test_validate_upload_005_non_numeric_amount`** — `amount='abc'`; `AmountParseError` caught; assert `RowError(column='amount', code='UPLOAD_005')`.
4. **`test_validate_upload_006_negative_amount`** — `amount=-1`; assert `RowError(column='amount', code='UPLOAD_006')`.
5. **`test_validate_zero_amount_accepted`** — `amount=0` with `allow_zero=True`; assert `ValidationResult.valid == True` (CR-012).

### `test_service.py` (integration)

1. **`test_upload_success_creates_version_1`** — valid `.xlsx`, Open cycle, correct dept code; assert `BudgetUpload.version=1`, `BudgetLine` rows in DB, audit entry, notification sent.
2. **`test_upload_second_version_increments`** — two successful uploads same `(cycle, org_unit)`; assert second has `version=2`.
3. **`test_upload_cycle_closed_raises_cycle_004`** — Closed cycle; assert `AppError(code='CYCLE_004')` before file parsing.
4. **`test_upload_oversized_file_raises_upload_001`** — content > `BC_MAX_UPLOAD_BYTES`; assert `AppError(code='UPLOAD_001')`.
5. **`test_upload_invalid_row_zero_persisted`** — 3-row file, row 2 has invalid amount; assert `BatchValidationError(UPLOAD_007)`; DB unchanged.
6. **`test_upload_notification_failure_does_not_invalidate`** — SMTP raises; assert upload row exists and response is the `BudgetUpload` (CR-029).

### `test_budget_uploads.py` (API)

1. **`test_upload_requires_filing_unit_manager_role`** — POST as `CompanyReviewer`; assert 403.
2. **`test_upload_valid_file_returns_201`** — POST valid `.xlsx` as `FilingUnitManager` for correct unit; assert 201 with upload payload.
3. **`test_list_versions_scoped`** — `FilingUnitManager` for unit A requests versions for unit B; assert empty list or 403.
4. **`test_upload_invalid_rows_returns_400_with_details`** — POST bad file; assert 400, `error.code == 'UPLOAD_007'`, `details` contains row errors.
