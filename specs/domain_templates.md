# Spec: domain/templates (M3)

**Batch:** 5
**Complexity:** Complex

## 1. Module Paths & Test Paths

| File | Test |
|---|---|
| `backend/src/app/domain/templates/service.py` | `backend/tests/unit/templates/test_service.py`, `backend/tests/integration/templates/test_service.py` |
| `backend/src/app/domain/templates/builder.py` | `backend/tests/unit/templates/test_builder.py` |
| `backend/src/app/domain/templates/models.py` | n/a |
| `backend/src/app/api/v1/templates.py` | `backend/tests/api/test_templates.py` |

---

## 2. Functional Requirements

### FR-009 — Template Generation

- **Trigger:** Called by the open-cycle orchestrator (Batch 6 `api/v1/orchestrators/open_cycle.py`) via `TemplateService.generate_for_cycle(cycle, filing_units, user)`. Called only for filing units passed in (orchestrator already excludes `0000` and excluded units).
- **Scope (CR-009):** For each filing unit, generate an Excel workbook containing **operational accounts ONLY** — no `personnel` category columns, no `shared_cost` category columns. Filtered via `AccountService.get_operational_codes_set()`.
- **Prefill actuals:** Each row in the workbook corresponds to one operational account code. The `actual_expenses` value for `(cycle_id, org_unit_id, account_code)` is prefilled. If no actual expense record exists for a row, display `0` (not blank, CR-034).
- **Zero-actual boundary (CR-034):** Template is generated even when ALL actuals are zero. The workbook is not skipped.
- **Per-unit failure isolation:** If generation of one unit's template fails (I/O error, unexpected data), record `status='generation_error'` and `error` message in the returned `TemplateGenerationResult` for that unit. Other units continue. Generation is NOT aborted globally.
- **Storage:** The built workbook bytes are saved via `infra.storage.save(category='templates', filename=...)`. The returned storage key is persisted in the `ExcelTemplate` ORM row with `file_path`.
- **Uniqueness:** Each `(cycle_id, org_unit_id)` has at most one active `ExcelTemplate` row. `regenerate` replaces it.

### FR-010 — Template Download

- **Authorization (RBAC):** Route declares `Depends(RBAC.require_role(FilingUnitManager, UplineReviewer, FinanceAdmin, SystemAdmin))`. Service additionally calls `RBAC.scoped_org_units(user, db)` to verify the requesting user's scope includes `org_unit_id` (CR-011). If not, raises `ForbiddenError(code='RBAC_002')`.
- **Not-yet-generated (TPL_002):** If no `ExcelTemplate` row exists for `(cycle_id, org_unit_id)` OR `status='generation_error'`, raises `AppError(code='TPL_002', message='Template not yet generated')`.
- **Download:** Reads file bytes via `infra.storage.read(template.file_path)`. Returns `(filename, bytes)` tuple. Filename format: `{org_unit_code}_{fiscal_year}_budget_template.xlsx`.
- **Download count:** Increments `ExcelTemplate.download_count` and updates `last_downloaded_at = now_utc()` in DB. Commits before returning.
- **Audit:** `AuditAction.TEMPLATE_DOWNLOAD` written after commit.

---

## 3. Exports

```python
# domain/templates/service.py

async def generate_for_cycle(
    cycle: BudgetCycle,
    filing_units: list[OrgUnit],
    user: User,
) -> list[TemplateGenerationResult]:
    """Generate Excel templates for all provided filing units.

    For each unit, builds an openpyxl workbook (operational accounts only,
    prefilled actuals), saves via infra.storage, and persists an ExcelTemplate
    row. Per-unit failures are captured as generation_error without aborting
    other units.

    Args:
        cycle: The BudgetCycle (must be Open; caller guarantees this).
        filing_units: OrgUnit list from CycleService.open (excludes 0000 and excluded units).
        user: User performing the generation (for audit).

    Returns:
        list[TemplateGenerationResult]: One entry per filing unit.
            Each entry has status='generated' or status='generation_error'.
    """

async def regenerate(
    cycle_id: UUID,
    org_unit_id: UUID,
    user: User,
) -> TemplateGenerationResult:
    """Regenerate the template for a single filing unit.

    Fetches the cycle and org unit, rebuilds the workbook, overwrites the
    existing ExcelTemplate row (or creates one), and saves the new file.

    Args:
        cycle_id: UUID of the target cycle.
        org_unit_id: UUID of the target org unit.
        user: User requesting regeneration (FinanceAdmin or SystemAdmin).

    Returns:
        TemplateGenerationResult: Result for the single unit.

    Raises:
        NotFoundError: Cycle or org unit not found.
        AppError(CYCLE_004): Cycle is not Open.
    """

async def download(
    cycle_id: UUID,
    org_unit_id: UUID,
    user: User,
) -> tuple[str, bytes]:
    """Download the generated template for the user's org unit.

    Validates RBAC scope, checks template existence, increments download_count.

    Args:
        cycle_id: UUID of the target cycle.
        org_unit_id: UUID of the target org unit.
        user: Authenticated user downloading.

    Returns:
        tuple[str, bytes]: (filename, workbook bytes).

    Raises:
        ForbiddenError(RBAC_002): User's scope does not include org_unit_id.
        AppError(TPL_002): Template not yet generated or in error state.
    """

# domain/templates/builder.py

def build_template(
    org_unit: OrgUnit,
    fiscal_year: int,
    operational_codes: list[AccountCode],
    actuals: dict[str, Decimal],
) -> bytes:
    """Build an openpyxl workbook for a single filing unit and return bytes.

    Prefills dept code, dept name, and per-account actual values. Accounts with
    no actual record receive 0. Uses infra.excel.write_workbook internally.
    Only operational-category codes are included (CR-009).

    Args:
        org_unit: ORM row for the filing unit (code, name).
        fiscal_year: Four-digit year label for the workbook.
        operational_codes: Ordered list of AccountCode rows (category=operational only).
        actuals: Map of account_code string -> actual Decimal amount for this unit/cycle.
                 Missing codes map to Decimal('0').

    Returns:
        bytes: The serialized .xlsx workbook bytes.
    """
```

**Pydantic model:**
```python
class TemplateGenerationResult(BaseModel):
    org_unit_id: UUID
    status: Literal["generated", "generation_error"]
    error: str | None = None
```

---

## 4. Imports

| Module | Symbols | Called by |
|---|---|---|
| `domain.cycles` | `CycleService.get`, `CycleStatus`, `BudgetCycle` | `regenerate` (fetch cycle), builder gets cycle info |
| `domain.accounts` | `AccountService.get_operational_codes_set`, `AccountCode` | `builder.build_template` — operational codes only (CR-009) |
| `domain.audit` | `AuditService.record`, `AuditAction` | After commit in `download`, `generate_for_cycle` |
| `core.security` | `User`, `Role`, `RBAC` | `download` scope check (CR-011, CR-032) |
| `infra.excel` | `write_workbook`, `workbook_to_bytes` | `builder.build_template` — workbook construction |
| `infra.storage` | `save`, `read` | `generate_for_cycle` (save), `download` (read) |
| `infra.db` | `get_session`, `AsyncSession` | All service methods |
| `core.errors` | `AppError`, `ForbiddenError`, `NotFoundError` | Error raising |
| `core.clock` | `now_utc` | `last_downloaded_at` timestamp |

### Required Call Order in `generate_for_cycle` (per-unit loop)

For each `org_unit` in `filing_units`:
1. Fetch `actuals: dict[str, Decimal]` for `(cycle_id, org_unit_id)` from `actual_expenses` table.
2. `bytes_data = builder.build_template(org_unit, fiscal_year, operational_codes, actuals)` — purely CPU-bound.
3. `storage_key = await infra.storage.save(category='templates', filename=..., content=bytes_data)`.
4. Upsert `ExcelTemplate` row with `file_path=storage_key`, `status='generated'`.
5. `await db.commit()`.
6. `await audit.record(AuditAction.TEMPLATE_DOWNLOAD, ...)` — (generation audit if needed).
7. Append `TemplateGenerationResult(org_unit_id=..., status='generated')` to results.

On `Exception` in steps 2–6 for a given unit:
- Catch, record `TemplateGenerationResult(org_unit_id=..., status='generation_error', error=str(e))`.
- Log `log.error('template.generation_failed', org_unit_id=..., error=...)`.
- Continue to next unit (do NOT re-raise).

### Required Call Order in `download`

1. `scoped = await RBAC.scoped_org_units(user, db)` → raise `RBAC_002` if `org_unit_id not in scoped`.
2. Fetch `ExcelTemplate` for `(cycle_id, org_unit_id)`.
3. If not found or `status != 'generated'` → raise `AppError(code='TPL_002')`.
4. `content = await infra.storage.read(template.file_path)`.
5. Update `template.download_count += 1`, `template.last_downloaded_at = now_utc()`.
6. `await db.commit()`.
7. `await audit.record(AuditAction.TEMPLATE_DOWNLOAD, ...)` (CR-006).
8. Return `(filename, content)`.

---

## 5. Side Effects

- Creates/upserts `excel_templates` rows on `generate_for_cycle` and `regenerate`.
- Saves `.xlsx` bytes to `infra.storage`.
- Increments `download_count` + updates `last_downloaded_at` on download.
- Writes `audit_logs` rows after commits.

---

## 6. Gotchas

- **CR-009 — Operational only:** `builder.build_template` receives `operational_codes` already filtered. The builder MUST NOT add columns for `personnel` or `shared_cost` categories. Calling `AccountService.get_operational_codes_set()` (not `get_codes_by_category`) is also acceptable — they return the same set.
- **CR-034 — Zero actuals:** If `actuals` dict has no entry for an account code, the builder MUST write `0` (the integer or Decimal zero), not an empty cell. An empty `actuals` dict still produces a workbook with all operational codes listed.
- **CR-010 — 0000 exclusion:** The `filing_units` list passed to `generate_for_cycle` already excludes `0000`. The service trusts this and does NOT re-filter. The orchestrator is responsible for the exclusion.
- **CR-011 — RBAC scope in download:** `RBAC.scoped_org_units(user, db)` is called once per request; the result is a set. The check is server-side; hiding the link in the frontend is not sufficient.
- **CR-017 — `is_filing_unit` flag:** Generation only targets units in the passed list; never enumerate from DB in the service loop.
- **Per-unit failure isolation:** `try/except Exception` wraps the per-unit block, but the outer `generate_for_cycle` method itself does NOT catch — if the `operational_codes` fetch fails (pre-loop), that is a fatal error and propagates.
- **`infra.excel` import allowed here (CR-024):** M3 templates generates Excel directly using openpyxl; it is the one domain module permitted to import from `infra.excel`. It does NOT use `infra.tabular` (that is for parsing imports).

---

## 7. Verbatim Outputs

- `TPL_002` — "Template not yet generated for this org unit and cycle."
- `RBAC_002` — "Access to this org unit's template is not permitted." (global handler message).
- `generation_error` status — surfaced in `TemplateGenerationResult.error` field and in the OpenCycleResponse generation summary (Batch 6 orchestrator).

---

## 8. Consistency Constraints

**CR-001 — Error code registry single source**
*"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
Codes raised: `TPL_002`, `RBAC_002`, `CYCLE_004` (via `assert_open` path in `regenerate`).

**CR-006 — Audit AFTER commit, BEFORE return**
*"This service commits the DB transaction first, then calls `audit.record(...)`, then returns. If audit fails, the entire operation is rolled back (audit failure = cannot honor FR-023)."*
Applies to: `download`, `generate_for_cycle` per-unit commit.

**CR-009 — Operational-only template generation**
*"The template builder pulls account codes via `accounts.get_operational_codes_set()` (or `get_codes_by_category('operational')`); personnel and shared_cost categories are NEVER written to the workbook."*

**CR-010 — 0000公司 excluded from filing-unit operations**
*"This module never treats `org_units WHERE level_code = '0000'` as a filing unit. Use the `is_filing_unit = TRUE` filter consistently — do NOT filter by level_code."*
This module trusts the `filing_units` list provided by the orchestrator and does not re-filter by level_code.

**CR-011 — Dashboard scoping uses RBAC.scoped_org_units**
*"This service calls `RBAC.scoped_org_units(user)` and applies the result as a WHERE filter on every query. URL-direct access to org units outside the user's scope returns an empty result set or 403 — never the unfiltered data."*
Applies to: `download`.

**CR-017 — Filing-unit lookup by `is_filing_unit` flag, NOT by `level_code` set**
*"All filing-unit queries use `WHERE is_filing_unit = TRUE`. The `level_code` is informational."*
This module receives its filing unit list from the orchestrator; it does not perform its own filing-unit queries.

**CR-034 — `actual_expenses` zero-row template generation**
*"`generate_for_cycle` produces a template even when `actual_expenses` is empty for the (cycle, org_unit). Empty rows display `0`, and the full operational account list is still rendered."*

---

## 9. Tests

### `test_builder.py` (unit)

1. **`test_build_template_contains_only_operational_codes`** — seed operational × 3, personnel × 2; `build_template` called with operational codes; parse resulting workbook; assert no personnel-category rows present (CR-009).
2. **`test_build_template_prefills_actuals`** — provide `actuals={'5101': Decimal('1000.00')}`; assert cell for `5101` contains `1000.00`.
3. **`test_build_template_zero_when_no_actual`** — `actuals={}` with 3 operational codes; assert all amount cells contain `0` (CR-034).
4. **`test_build_template_includes_dept_code_and_name`** — `org_unit.code='4023'`, `org_unit.name='業務部'`; parse workbook; assert dept code and name cells are populated.

### `test_service.py` (unit — `generate_for_cycle`)

1. **`test_generate_for_cycle_success_all_units`** — 2 filing units; both generate; results both `status='generated'`; 2 storage save calls; 2 `ExcelTemplate` DB rows.
2. **`test_generate_per_unit_failure_continues`** — `infra.storage.save` raises for unit 2; assert unit 1 `status='generated'`, unit 2 `status='generation_error'`; no exception propagated.
3. **`test_generate_zero_actuals_still_generates`** — empty `actual_expenses` table; assert template still created with `0` values (CR-034).

### `test_service.py` (unit — `download`)

1. **`test_download_success_increments_count`** — valid cycle/unit/user with scope; assert content returned, `download_count=1`, audit entry created.
2. **`test_download_wrong_scope_raises_rbac_002`** — `scoped_org_units` returns empty set; assert `ForbiddenError(code='RBAC_002')`.
3. **`test_download_not_generated_raises_tpl_002`** — no `ExcelTemplate` row; assert `AppError(code='TPL_002')`.
4. **`test_download_generation_error_raises_tpl_002`** — `ExcelTemplate.status='generation_error'`; assert `AppError(code='TPL_002')`.

### `test_templates.py` (API)

1. **`test_download_requires_authentication`** — unauthenticated GET; assert 401.
2. **`test_download_scoped_user_success`** — `FilingUnitManager` for correct unit; assert 200, `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
3. **`test_download_wrong_unit_403`** — `FilingUnitManager` for different unit; assert 403.
4. **`test_regenerate_requires_finance_admin`** — POST regenerate as `FilingUnitManager`; assert 403.
