# Spec: domain/accounts (M2)

**Batch:** 3
**Complexity:** Complex

## 1. Module Paths & Test Paths

| File | Test |
|---|---|
| `backend/src/app/domain/accounts/service.py` | `backend/tests/unit/accounts/test_service.py`, `backend/tests/integration/accounts/test_service.py` |
| `backend/src/app/domain/accounts/validator.py` | `backend/tests/unit/accounts/test_validator.py` |
| `backend/src/app/domain/accounts/models.py` | n/a |
| `backend/src/app/api/v1/accounts.py` | `backend/tests/api/test_accounts.py` |

---

## 2. Functional Requirements

### FR-007 — Account Master CRUD

- **Input:** `AccountCodeWrite` Pydantic schema — `code` (str, required), `name` (str, required), `category` (`AccountCategory` enum, required), `level` (int, required).
- **Upsert semantics:** `code` is the natural key. If the code exists, update `name`, `category`, `level`. If it does not exist, insert.
- **Categories (enum `AccountCategory`, StrEnum):** `operational`, `personnel`, `shared_cost`. This is the closed vocabulary; no other values are valid.
- **Level:** Integer representing organizational level (no range constraint in PRD; store as-is).
- **List with optional filter:** `AccountService.list(category=None)` returns all codes; pass an `AccountCategory` to filter.
- **Audit:** Each upsert writes `AuditAction.ACCOUNT_UPSERT` after commit.

### FR-008 — Bulk Actuals Import (collect-then-report, integral commit)

- **Input file formats:** CSV (UTF-8 only) or XLSX. Dispatched via `infra.tabular.parse_table(filename, content)`.
- **Expected columns (case-insensitive after `clean_cell` + `.lower()`):** `org_unit_code` (maps to `dept_id`), `account_code`, `amount`. Unknown headers reject with a batch-level error before row iteration.
- **Cycle state check (CR-005):** `await cycles.assert_open(cycle_id)` is the FIRST call in `import_actuals`, before any file parsing or DB work.
  - **Batch 3 dependency note:** `CycleService` ships in Batch 4. In Batch 3, `assert_open` is imported with a `TYPE_CHECKING` guard and called via lazy import inside `import_actuals`:
    ```python
    from __future__ import annotations
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from app.domain.cycles.service import CycleService
    ```
    The actual import at runtime uses `importlib` or a deferred DI parameter. The spec author flags this: **Batch 4 must verify that the import chain resolves without circular dependency when cycles ships.** The recommended pattern is to pass `cycle_service: CycleService` as a constructor argument to `AccountService` (injected via FastAPI `Depends`) so no import-time coupling exists.
- **Validation (ActualsImportValidator, collect-then-report — CR-004):**
  - Row-level errors emit `RowError` objects collected before any DB write.
  - Error codes for this module: all `ACCOUNT_002` (single code for row-level failures; reason field distinguishes the specific problem).
  - Specific error conditions:
    - `org_unit_code` not found in `org_unit_code_to_id_map(db)` → `RowError(row=N, column='org_unit_code', code='ACCOUNT_002', reason='Unknown org unit code: <value>')`.
    - `account_code` not found in `AccountCode` table → `RowError(row=N, column='account_code', code='ACCOUNT_002', reason='Unknown account code: <value>')`.
    - `amount` parse failure (`AmountParseError`) → `RowError(row=N, column='amount', code='ACCOUNT_002', reason=str(e))`. `parse_amount` called with `allow_zero=True` (actuals may be zero — FR-008 does not exclude zero).
    - Empty `org_unit_code` or `account_code` after `clean_cell` → `RowError(row=N, column=<col>, code='ACCOUNT_002', reason='Required cell is empty')`.
  - After all rows processed: if `result.errors` is non-empty → raise `BatchValidationError(code='ACCOUNT_002', errors=result.errors)` and persist NOTHING.
- **Integral commit (CR-004):** Zero rows persisted on any failure. The persisting transaction wraps `INSERT actual_expense header (if any) + INSERT actual_expense lines` only — no insert-then-validate pattern.
- **On success:** `await db.commit()`, then `await audit.record(AuditAction.ACTUALS_IMPORT, ...)`, then return `ImportSummary`.
- **ImportSummary:** `row_count` (int), `org_units_affected` (list of org unit codes updated), `cycle_id` (UUID).

### Pre-implemented methods for downstream consumers

The following two methods MUST be implemented in Batch 3 even though their first consumers ship in Batch 5 (M3 templates) and Batch 5 (M4/M5/M6 importers). This avoids blocking Batch 5.

- `AccountService.get_operational_codes_set() -> set[str]`: Returns the set of `code` values where `category = AccountCategory.operational`. Used by M3 template builder (CR-009) and M4 budget upload validator.
- `AccountService.get_codes_by_category(category: AccountCategory) -> set[str]`: Returns the set of `code` values for the given category. Used by M5 (`AccountCategory.personnel`) and M6 (`AccountCategory.shared_cost`) validators.

---

## 3. Exports

```python
# domain/accounts/models.py

class AccountCategory(StrEnum):
    """Closed vocabulary for account categories (CR-020 owner)."""
    operational = "operational"
    personnel = "personnel"
    shared_cost = "shared_cost"

# domain/accounts/service.py

async def list(category: AccountCategory | None = None) -> list[AccountCode]:
    """Return all account codes, optionally filtered by category.

    Args:
        category: Optional AccountCategory filter. None returns all.

    Returns:
        list[AccountCode]: ORM rows ordered by code.
    """

async def upsert(data: AccountCodeWrite) -> AccountCode:
    """Create or update an account code record.

    Args:
        data: AccountCodeWrite schema with code, name, category, level.

    Returns:
        AccountCode: Upserted ORM row.

    Raises:
        AppError: Validation failure on unknown category (handled by Pydantic).
    """

async def get_by_code(code: str) -> AccountCode:
    """Fetch a single account code by its code string.

    Args:
        code: Account code string (e.g. '5101').

    Returns:
        AccountCode: ORM row.

    Raises:
        NotFoundError: Code does not exist.
    """

async def get_operational_codes_set() -> set[str]:
    """Return the set of all operational-category account code strings.

    Returns:
        set[str]: Code strings for AccountCategory.operational.
    """

async def get_codes_by_category(category: AccountCategory) -> set[str]:
    """Return the set of account code strings for the given category.

    Args:
        category: AccountCategory enum member.

    Returns:
        set[str]: Code strings for the specified category.
    """

async def import_actuals(
    cycle_id: UUID,
    filename: str,
    content: bytes,
    user: User,
    cycle_service: "CycleService",
) -> ImportSummary:
    """Bulk import actual expenses from CSV or XLSX for a cycle.

    Validates the cycle is open, parses the file, validates all rows
    (collect-then-report), then commits all rows or raises on any error.

    Args:
        cycle_id: Target cycle UUID.
        filename: Original filename (used for format dispatch).
        content: Raw file bytes.
        user: Authenticated user performing the import.
        cycle_service: Injected CycleService (avoids circular import at module load).

    Returns:
        ImportSummary: Row count and affected org units.

    Raises:
        AppError(CYCLE_004): Cycle is not Open.
        BatchValidationError(ACCOUNT_002): One or more row errors; nothing persisted.
    """

# domain/accounts/validator.py

def validate(
    rows: list[dict],
    *,
    org_unit_codes: dict[str, UUID],
    account_codes: set[str],
) -> ValidationResult:
    """Validate rows from a parsed actuals import file.

    Args:
        rows: Parsed rows from infra.tabular.parse_table.
        org_unit_codes: Map of org_unit.code -> UUID from org_unit_code_to_id_map.
        account_codes: Set of valid account code strings from AccountService.

    Returns:
        ValidationResult: .valid is True only if errors list is empty.
    """
```

---

## 4. Imports

| Module | Symbols | Called by |
|---|---|---|
| `infra.db` | `get_session`, `AsyncSession` | All service methods |
| `infra.tabular` | `parse_table` | `import_actuals` — CSV/XLSX dispatch (CR-024) |
| `infra.storage` | `save` | Optionally store the raw import file; optional per design — if stored, use `save(category='actuals', ...)` |
| `domain._shared.row_validation` | `RowError`, `ValidationResult`, `clean_cell`, `parse_amount`, `AmountParseError` | `ActualsImportValidator.validate` |
| `domain._shared.queries` | `org_unit_code_to_id_map` | `import_actuals` — translate `org_unit_code` column to UUIDs |
| `domain.audit` | `AuditService.record`, `AuditAction` | After commit in `upsert` and `import_actuals` |
| `core.security` | `User`, `Role`, `RBAC` | Route RBAC enforcement |
| `core.errors` | `BatchValidationError`, `NotFoundError`, `AppError` | Error raising |

### Required Call Order in `import_actuals` (CR-004, CR-005)

1. `await cycle_service.assert_open(cycle_id)` — raises `CYCLE_004` if not Open. **This is the first call.** (CR-005)
2. `rows = await parse_table(filename, content)` — file parsing (may raise `InfraError` on malformed file).
3. `org_unit_codes = await org_unit_code_to_id_map(db)` — single query for translation map.
4. `result = ActualsImportValidator.validate(rows, org_unit_codes=org_unit_codes, account_codes=account_codes)` — full validation before any DB write.
5. If `not result.valid`: raise `BatchValidationError(code='ACCOUNT_002', errors=result.errors)`. **Zero rows persisted.** (CR-004)
6. Open persisting transaction; `INSERT` `actual_expenses` rows.
7. `await db.commit()`.
8. `await audit.record(AuditAction.ACTUALS_IMPORT, ...)`. (CR-006)
9. Return `ImportSummary`.

**Rationale:** Step 1 must precede file parsing per CR-005. Steps 4–5 must complete before step 6 per CR-004 integral commit. Step 8 must follow step 7 per CR-006.

---

## 5. Side Effects

- Writes/upserts `account_codes` table on `upsert`.
- Writes `actual_expenses` rows on successful `import_actuals`.
- Writes `audit_logs` rows after each commit.

---

## 6. Gotchas

- **`AccountCategory` comparison must use enum members (CR-020).** `AccountCategory.operational` not the string `'operational'`. SQL queries pass the enum value to SQLAlchemy's enum binding.
- **`parse_amount` for actuals uses `allow_zero=True`** (FR-008 actuals may be zero). This is the opposite of personnel (FR-024) and shared_cost (FR-027) which use `allow_zero=False`. Do not copy the wrong default.
- **`get_operational_codes_set` and `get_codes_by_category`** are pre-implemented for Batch 5 consumers. They must return real data from the DB, not stubs.
- **Circular import risk with `CycleService`.** Cycles ship in Batch 4. The recommended resolution is constructor injection (pass `cycle_service` as a FastAPI `Depends` parameter) so no module-level import of `domain.cycles` occurs from `domain.accounts`. Flag for Batch 4 review.
- **Header normalization:** before row validation, normalize incoming column headers using `clean_cell` + `.lower()`. Reject with a batch-level error (not a row error) if required columns are missing.
- **`import_actuals` replaces or supplements actuals?** The PRD says "批次匯入各單位當年度各會科實際費用資料" — this is a full replacement of actuals for the given `(cycle_id, org_unit_code, account_code)` combinations, not an append. Use upsert semantics per `(cycle_id, org_unit_id, account_code_id)`.
- **Currency: `reporting_currency` is informational only (CR-023).** Do not convert amounts; store raw values.

---

## 7. Verbatim Outputs (from PRD §4.2)

- FR-008 batch validation error: raised as `BatchValidationError(code='ACCOUNT_002')` with row-level `RowError` list. Error envelope shape follows architecture §3 collect-then-report pattern.
- No user-visible strings specific to accounts in PRD §4.2 beyond the error code.

---

## 8. Consistency Constraints

**CR-001 — Error code registry single source**
*"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
Applies to: `ACCOUNT_002`, `CYCLE_004` (raised by `cycles.assert_open`, not owned here).

**CR-004 — Validation BEFORE persistence (collect-then-report)**
*"This service performs validation entirely before opening the persisting transaction. On any `RowError`, raise `BatchValidationError` and persist zero rows. The persisting transaction wraps `INSERT upload header + INSERT lines` only — never INSERT-then-validate."*

**CR-005 — Cycle state assertion BEFORE write operations**
*"This service's first action is `await cycles.assert_open(cycle_id)`. Subsequent steps may assume the cycle is Open."*

**CR-006 — Audit AFTER commit, BEFORE return**
*"This service commits the DB transaction first, then calls `audit.record(...)`, then returns. If audit fails, the entire operation is rolled back (audit failure = cannot honor FR-023)."*
Applies to: `upsert` and `import_actuals`.

**CR-009 — Operational-only template generation (FR-009)**
*"The template builder pulls account codes via `accounts.get_operational_codes_set()` (or `get_codes_by_category('operational')`); personnel and shared_cost categories are NEVER written to the workbook."*
This module PROVIDES `get_operational_codes_set()` and `get_codes_by_category()` for M3 to consume.

**CR-020 — Account-category lookup is exact-match on enum value**
*"All category comparisons use the `AccountCategory` enum members directly (`AccountCategory.personnel` etc.); no string literals. SQL queries pass the enum value to SQLAlchemy's enum binding."*
This module OWNS `AccountCategory`.

**CR-021 — Robust amount parsing wrapped in try/except**
*"Every call to `parse_amount` is wrapped in `try/except AmountParseError`, and the caught exception becomes a `RowError(row=..., column='amount', code='UPLOAD_005|PERS_003|SHARED_003|ACCOUNT_002', reason=str(e))`."*
For this module: `RowError(code='ACCOUNT_002')`.

**CR-022 — `clean_cell` for every user-supplied string field**
*"Every cell read from openpyxl or `csv.DictReader` is passed through `clean_cell` before comparison. Direct `==` comparisons on raw cell values are forbidden."*

**CR-023 — Currency code accepted but not converted (PRD §2.3)**
*"`reporting_currency` is validated as a 3-letter ISO 4217 code on cycle create and stored as-is. NO conversion logic anywhere — sums use the raw amounts. Default `'TWD'`."*

**CR-024 — File extension dispatch lives in `infra/tabular` only**
*"File parsing is delegated to `infra.tabular.parse_table(filename, content)`. Do not import `infra.csv_io` or `infra.excel` directly from a domain importer."*

---

## 9. Tests

### `test_service.py` (unit)

1. **`test_list_all_accounts`** — seed 3 accounts with different categories; `list()` returns all 3.
2. **`test_list_accounts_filtered_by_category`** — seed `operational` × 2 and `personnel` × 1; `list(AccountCategory.operational)` returns 2.
3. **`test_upsert_insert_new_code`** — upsert a new code; assert row exists in DB with correct fields; `ACCOUNT_UPSERT` audit entry created after commit.
4. **`test_upsert_update_existing_code`** — upsert same code twice with different `name`; assert only one row, second name wins.
5. **`test_get_by_code_not_found`** — call `get_by_code('NONEXISTENT')`; assert `NotFoundError`.

### `test_service.py` — `import_actuals` (integration)

1. **`test_import_actuals_success`** — valid 3-row CSV; assert 3 `actual_expense` rows in DB; `ImportSummary.row_count == 3`; `ACTUALS_IMPORT` audit entry.
2. **`test_import_actuals_cycle_closed_raises_cycle_004`** — cycle is Closed; assert `AppError(CYCLE_004)` raised before any file parsing.
3. **`test_import_actuals_invalid_row_raises_account_002`** — 3-row file where row 2 has unknown `account_code`; assert `BatchValidationError(code='ACCOUNT_002')` with one error at row 2; DB row count unchanged.
4. **`test_import_actuals_zero_amount_accepted`** — row with `amount=0`; `allow_zero=True`; assert import succeeds.
5. **`test_import_actuals_empty_org_unit_code`** — row with empty `org_unit_code`; assert `BatchValidationError` with `RowError(column='org_unit_code', code='ACCOUNT_002')`.

### `test_validator.py` (unit — per RowError code)

1. **`test_validate_unknown_org_unit_code`** — row with `org_unit_code` not in `org_unit_codes` map; assert `RowError(column='org_unit_code', code='ACCOUNT_002')` at correct row number.
2. **`test_validate_unknown_account_code`** — row with `account_code` not in `account_codes` set; assert `RowError(column='account_code', code='ACCOUNT_002')` at correct row number.
3. **`test_validate_non_numeric_amount`** — row with `amount='abc'`; `AmountParseError` caught; assert `RowError(column='amount', code='ACCOUNT_002')`.
4. **`test_validate_empty_required_cell`** — row with `account_code=None`; assert `RowError(column='account_code', code='ACCOUNT_002', reason contains 'empty')`.
5. **`test_validate_all_valid_rows`** — 5 valid rows; assert `ValidationResult.valid == True` and `errors == []`.

### `test_accounts.py` (API)

1. **`test_upsert_account_requires_system_admin`** — POST as `FinanceAdmin`; assert 403.
2. **`test_upsert_account_as_system_admin`** — POST as `SystemAdmin`; assert 201 with account payload.
3. **`test_list_accounts_public`** — GET as any authenticated user; assert 200 with list.
4. **`test_import_actuals_valid_file`** — POST multipart CSV as `SystemAdmin`; assert 200 with `ImportSummary`.
5. **`test_import_actuals_invalid_rows_returns_400`** — POST CSV with bad row; assert 400 with `error.code == 'ACCOUNT_002'` and `details` list.
