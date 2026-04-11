# Spec: domain/cycles (M1)

**Batch:** 4
**Complexity:** Complex

## 1. Module Paths & Test Paths

| File | Test |
|---|---|
| `backend/src/app/domain/cycles/service.py` | `backend/tests/unit/cycles/test_service.py`, `backend/tests/integration/cycles/test_service.py` |
| `backend/src/app/domain/cycles/reminders.py` | `backend/tests/integration/cycles/test_reminders.py` |
| `backend/src/app/domain/cycles/state_machine.py` | `backend/tests/unit/cycles/test_state_machine.py` |
| `backend/src/app/domain/cycles/models.py` | n/a |
| `backend/src/app/domain/cycles/filing_units.py` | `backend/tests/unit/cycles/test_filing_units.py` |
| `backend/src/app/infra/db/repos/budget_uploads_query.py` | `backend/tests/integration/infra/test_unsubmitted_query.py` |
| `backend/src/app/api/v1/cycles.py` | `backend/tests/api/test_cycles.py` |
| `backend/src/app/api/v1/admin/org_units.py` | `backend/tests/api/test_admin_org_units.py` |

---

## 2. Functional Requirements

### FR-001 — Create Budget Cycle (Draft)

- **Input:** `fiscal_year` (int), `deadline` (date), `reporting_currency` (str, 3-letter ISO 4217, default `'TWD'`).
- **UNIQUE constraint:** One non-Closed cycle per `fiscal_year`. The DB has `UNIQUE INDEX` on `(fiscal_year)` WHERE `status != 'closed'`.
- **On conflict:** Raises `ConflictError(code='CYCLE_001', message='A non-closed cycle already exists for this fiscal year')`.
- **Initial state:** `CycleStatus.draft`.
- **Audit:** Write `AuditAction.CYCLE_OPEN` (or a dedicated `CYCLE_CREATE` if added to enum) after commit.
- **CR-023:** `reporting_currency` validated as 3-letter alpha string; stored as-is with no conversion.

### FR-002 — List Filing Units

- **Rule:** Filing units are all `org_units WHERE is_filing_unit = TRUE`. The `is_filing_unit` boolean is the source of truth (CR-017). `6000`, `5000`, and `0000` level codes are never filing units (CR-010).
- **Manager check (CR-008):** `list_filing_units(cycle_id)` first enumerates ALL `org_units WHERE is_filing_unit = TRUE`, then LEFT JOINs to users to compute `has_manager` (whether at least one User row has `org_unit_id = this unit` and a manager-equivalent role). Returns `has_manager=False` rows without filtering them out.
- **`excluded_for_cycle_ids`:** Each `OrgUnit` has a JSONB column `excluded_for_cycle_ids: list[UUID]`. If `cycle_id IN excluded_for_cycle_ids`, the unit is shown in the list with `excluded=True` but does NOT block the `open` transition.
- **Block condition:** If any filing unit has `has_manager=False` AND `excluded=False` for this cycle, `CycleService.open` raises `CYCLE_002`.
- **Output:** `list[FilingUnitInfo]` — each with `org_unit_id`, `code`, `name`, `has_manager`, `excluded`, `warnings`.

### FR-003 — Draft → Open Transition

- **Pre-condition:** Cycle must be in `CycleStatus.draft`. If not, raises `ConflictError(code='CYCLE_003')`.
- **Manager gate:** Before transitioning, calls `filing_units.check_all_have_managers(cycle_id)` which raises `CYCLE_002` if any non-excluded filing unit lacks a manager.
- **Transition:** Sets `status = 'open'`, `opened_at = now_utc()`.
- **Return value:** `tuple[BudgetCycle, list[OrgUnit]]` — the updated cycle + list of filing units (excluding those with `is_filing_unit = FALSE` or `excluded=True` for this cycle, and excluding `0000`). This list is consumed by the orchestrator (Batch 6) to drive template generation and notification dispatch. The cycles service DOES NOT call template generation or notifications directly.
- **Audit:** `AuditAction.CYCLE_OPEN` after commit.

### FR-005 — Reminder Schedule

- **Default schedule:** `days_before = [7, 3, 1]` set automatically when a cycle is created (`default_on`).
- **PATCH endpoint:** `PATCH /api/v1/cycles/{id}/reminders` — replaces `days_before` list. Empty list `[]` disables reminders entirely.
- **Cron (FR-020):** A daily APScheduler cron at `09:00` server TZ (CR-038) scans all Open cycles, computes which ones have a reminder due today (`deadline - today_date IN days_before`), and calls `dispatch_deadline_reminders()`.
- **Dispatch:** For each due cycle, fetches unsubmitted filing units via `infra.db.repos.budget_uploads_query.unsubmitted_for_cycle(db, cycle_id)` (CR-026). For each unit, resolves manager + upline reviewer recipients, then calls `NotificationService.send(NotificationTemplate.deadline_reminder, ...)`.
- **Already-uploaded exclusion (CR-027):** `unsubmitted_for_cycle` returns only units with ZERO uploads; already-uploaded units are excluded automatically.
- **Cron exception isolation (CR-035):** The cron callback wraps its entire body in `try/except Exception`. On exception: `log.error('scheduler.callback_failed', ...)` and return — never re-raise.

### FR-006 — Open → Closed Transition + Reopen

- **Close:** `CycleService.close(cycle_id, user)` transitions `status = 'closed'`, `closed_at = now_utc()`. Usable by FinanceAdmin or triggered automatically when `deadline` passes (cron).
- **Post-Closed writes:** Any module calling `assert_open(cycle_id)` after closure gets `AppError(code='CYCLE_004')`. This covers budget uploads, personnel imports, shared cost imports.
- **Reopen (CR-037):** `CycleService.reopen(cycle_id, reason, user)` is restricted to `SystemAdmin` only. Raises `CYCLE_005` if `(now_utc() - cycle.closed_at).days > BC_REOPEN_WINDOW_DAYS`. Uses `closed_at` — NOT `created_at` or `updated_at`.
- **Audit:** `AuditAction.CYCLE_CLOSE` and `AuditAction.CYCLE_REOPEN` (if reopen is added to enum) after commit.

### `assert_open` — Consumed by Batch 5 importers

- **Signature:** `async def assert_open(cycle_id: UUID) -> None`
- **Behavior:** Fetches `BudgetCycle` by id; raises `AppError(code='CYCLE_004')` if `status != 'open'`. Also raises `NotFoundError` if cycle not found.
- **Contract (CR-005):** Every write service in M4, M5, M6 MUST call this as its FIRST action.

---

## 3. Exports

```python
# domain/cycles/models.py

class CycleStatus(StrEnum):
    """Lifecycle states of a BudgetCycle."""
    draft = "draft"
    open = "open"
    closed = "closed"

# domain/cycles/service.py

async def create(
    fiscal_year: int,
    deadline: date,
    reporting_currency: str,
    user: User,
) -> BudgetCycle:
    """Create a new Draft budget cycle.

    Args:
        fiscal_year: Four-digit fiscal year (e.g. 2026).
        deadline: Submission deadline date.
        reporting_currency: 3-letter ISO 4217 currency code. Default 'TWD'.
        user: Authenticated user creating the cycle (FinanceAdmin or SystemAdmin).

    Returns:
        BudgetCycle: Newly created ORM row in Draft state.

    Raises:
        ConflictError(CYCLE_001): A non-closed cycle already exists for this fiscal_year.
    """

async def open(cycle_id: UUID) -> tuple[BudgetCycle, list[OrgUnit]]:
    """Transition a Draft cycle to Open state.

    Checks all non-excluded filing units have managers before transitioning.
    Returns filing unit list (excluding 0000 and excluded units) for the
    orchestrator to drive template generation and notifications.

    Args:
        cycle_id: UUID of the target cycle.

    Returns:
        tuple[BudgetCycle, list[OrgUnit]]: Updated cycle + actionable filing units.

    Raises:
        ConflictError(CYCLE_003): Cycle is not in Draft state.
        AppError(CYCLE_002): One or more non-excluded filing units lack a manager.
    """

async def close(cycle_id: UUID, user: User) -> BudgetCycle:
    """Transition an Open cycle to Closed state.

    Args:
        cycle_id: UUID of the target cycle.
        user: Authenticated user closing the cycle.

    Returns:
        BudgetCycle: Updated ORM row with status=closed, closed_at set.

    Raises:
        ConflictError(CYCLE_003): Cycle is not in Open state.
    """

async def reopen(cycle_id: UUID, reason: str, user: User) -> BudgetCycle:
    """Reopen a Closed cycle within the reopen window. SystemAdmin only.

    Args:
        cycle_id: UUID of the target cycle.
        reason: Mandatory reason string for audit trail.
        user: SystemAdmin performing the reopen.

    Returns:
        BudgetCycle: Updated ORM row with status=open.

    Raises:
        AppError(CYCLE_005): Reopen window has elapsed (> BC_REOPEN_WINDOW_DAYS since closed_at).
        ConflictError(CYCLE_003): Cycle is not in Closed state.
    """

async def get(cycle_id: UUID) -> BudgetCycle:
    """Fetch a cycle by UUID.

    Args:
        cycle_id: UUID of the cycle.

    Returns:
        BudgetCycle: ORM row.

    Raises:
        NotFoundError: Cycle does not exist.
    """

async def get_status(cycle_id: UUID) -> CycleStatus:
    """Return the current status of a cycle.

    Args:
        cycle_id: UUID of the cycle.

    Returns:
        CycleStatus: Current status enum value.

    Raises:
        NotFoundError: Cycle does not exist.
    """

async def list_filing_units(cycle_id: UUID) -> list[FilingUnitInfo]:
    """List all filing units for a cycle with manager and exclusion flags.

    Delegates to filing_units.resolve_filing_units(cycle_id).

    Args:
        cycle_id: UUID of the cycle.

    Returns:
        list[FilingUnitInfo]: All is_filing_unit=TRUE units with has_manager + excluded fields.
    """

async def assert_open(cycle_id: UUID) -> None:
    """Assert a cycle is in Open state; raise CYCLE_004 otherwise.

    Called as the first action by every write service (CR-005).

    Args:
        cycle_id: UUID of the cycle.

    Raises:
        AppError(CYCLE_004): Cycle is not Open.
        NotFoundError: Cycle does not exist.
    """

async def set_reminder_schedule(
    cycle_id: UUID,
    days_before: list[int],
) -> list[CycleReminderSchedule]:
    """Set or replace the reminder schedule for a cycle.

    An empty list disables reminders. Replaces all existing schedules.

    Args:
        cycle_id: UUID of the cycle.
        days_before: Days before deadline to send reminder. [] disables.

    Returns:
        list[CycleReminderSchedule]: Persisted schedule rows.
    """

async def dispatch_deadline_reminders() -> DispatchSummary:
    """Cron callback: scan Open cycles and send due deadline reminders.

    Called daily at 09:00 server TZ by APScheduler. Finds cycles where
    (deadline - today) IN days_before, fetches unsubmitted filing units,
    resolves recipients, and sends deadline_reminder notifications.

    Returns:
        DispatchSummary: Count of cycles checked, reminders dispatched.
    """

# domain/cycles/filing_units.py

async def resolve_filing_units(
    cycle_id: UUID,
    db: AsyncSession,
) -> list[FilingUnitInfo]:
    """Enumerate all filing units with manager presence and exclusion flags.

    Queries org_units WHERE is_filing_unit = TRUE, LEFT JOINs to users
    to determine has_manager. Checks excluded_for_cycle_ids JSONB for
    the given cycle_id.

    Args:
        cycle_id: UUID of the cycle (used for exclusion check).
        db: Async DB session.

    Returns:
        list[FilingUnitInfo]: All filing units. has_manager=False rows included.
    """

# infra/db/repos/budget_uploads_query.py

async def unsubmitted_for_cycle(
    db: AsyncSession,
    cycle_id: UUID,
) -> list[OrgUnit]:
    """Return filing units that have not uploaded for a cycle.

    Queries org_units WHERE is_filing_unit = TRUE that have ZERO rows
    in budget_uploads for the given cycle_id.

    Args:
        db: Async DB session.
        cycle_id: UUID of the cycle to check.

    Returns:
        list[OrgUnit]: Units with no budget upload for this cycle.
    """
```

**Pydantic models:**
```python
class FilingUnitInfo(BaseModel):
    org_unit_id: UUID
    code: str
    name: str
    has_manager: bool
    excluded: bool
    warnings: list[str]

class DispatchSummary(BaseModel):
    cycles_checked: int
    reminders_dispatched: int
    errors: list[str]
```

---

## 4. Imports

| Module | Symbols | Called by |
|---|---|---|
| `domain.notifications` | `NotificationService.send`, `NotificationTemplate` | `dispatch_deadline_reminders`, reminder dispatch |
| `domain.audit` | `AuditService.record`, `AuditAction` | After commit in `create`, `open`, `close`, `reopen` |
| `core.security` | `User`, `Role`, `RBAC` | Route RBAC enforcement; `reopen` requires `SystemAdmin` |
| `infra.db` | `get_session`, `AsyncSession` | All service methods |
| `infra.scheduler` | `register_cron` | Register `dispatch_deadline_reminders` at app startup |
| `infra.db.repos.budget_uploads_query` | `unsubmitted_for_cycle` | `dispatch_deadline_reminders` (CR-026) |
| `core.clock` | `now_utc` | `close`, `reopen` window check, `opened_at` timestamp |
| `core.errors` | `AppError`, `ConflictError`, `NotFoundError` | Error raising |

### Required Call Order in `CycleService.open` (CR-005, CR-008)

1. Fetch `BudgetCycle`; raise `NotFoundError` if missing.
2. `state_machine.assert_transition(cycle.status, CycleStatus.draft, 'CYCLE_003')` — raises `CYCLE_003` if not Draft.
3. `filing_unit_infos = await filing_units.resolve_filing_units(cycle_id, db)` — enumerate ALL filing units (CR-008).
4. Check: any `info.has_manager == False and not info.excluded` → raise `CYCLE_002`.
5. Set `cycle.status = CycleStatus.open`, `cycle.opened_at = now_utc()`.
6. `await db.commit()`.
7. `await audit.record(AuditAction.CYCLE_OPEN, ...)` (CR-006).
8. Compute `actionable_units = [ou for ou in units if not excluded]` and return `(cycle, actionable_units)`.

**Rationale:** Step 3 must precede step 4 (CR-008 mandates enumeration before manager check). Steps 6–7 follow CR-006. The service DOES NOT call template or notification directly; the orchestrator in Batch 6 does.

### Required Call Order in `CycleService.reopen` (CR-037)

1. Fetch `BudgetCycle`; raise `NotFoundError` if missing.
2. Assert `cycle.status == CycleStatus.closed` → raise `CYCLE_003` otherwise.
3. `days_since_close = (now_utc() - cycle.closed_at).days` → raise `CYCLE_005` if > `settings.bc_reopen_window_days`. Uses `closed_at` (CR-037).
4. Set `cycle.status = CycleStatus.open`.
5. `await db.commit()`.
6. `await audit.record(AuditAction.CYCLE_REOPEN, ...)` (CR-006).
7. Return `cycle`.

---

## 5. Side Effects

- Creates `budget_cycles` row on `create`.
- Writes `cycle_reminder_schedules` rows on `set_reminder_schedule` (replaces existing).
- Registers APScheduler cron job for `dispatch_deadline_reminders` at app startup via `infra.scheduler.register_cron`.
- Calls `NotificationService.send_batch` for deadline reminders (side effect: `notifications` rows + SMTP calls).
- Writes `audit_logs` rows after each state-changing commit.
- PATCH `/admin/org-units/{id}` updates `excluded_for_cycle_ids` JSONB on `OrgUnit`.

---

## 6. Gotchas

- **`0000` is never a filing unit (CR-010, CR-017).** All filing-unit queries use `WHERE is_filing_unit = TRUE`. Never filter by `level_code IN (...)`. The `is_filing_unit` boolean is the authoritative source.
- **`excluded_for_cycle_ids` JSONB:** Stored as a JSON array of UUID strings on the `OrgUnit` table. When checking exclusion, compare `str(cycle_id)` against the serialized array — do not cast to Python UUID set inside SQL.
- **`assert_open` is called by M4/M5/M6 importers** in Batch 5. The import at module level from `domain.cycles.service` is safe because cycles (Batch 4) ships before Batch 5. No circular import risk here.
- **`CycleStatus` is a StrEnum.** SQL comparisons pass the enum value, not the string literal (CR-020 pattern extended here).
- **Cron isolation (CR-035):** The APScheduler callback must wrap its body in `try/except Exception`, log on error, and return — never re-raise. APScheduler does not restart a dead callback.
- **Timezone for cron (CR-038):** APScheduler must be initialized with `timezone=ZoneInfo(settings.bc_timezone)` (default `Asia/Taipei`). The expression `0 9 * * *` fires at 09:00 Taipei time, not UTC.
- **`dispatch_deadline_reminders` upline resolution:** Walk `parent_id` from each unsubmitted unit until an `UplineReviewer` or `FinanceAdmin` user is found. If the entire chain has no reviewer, log `WARN event=notification.no_upline_found` and continue (CR-028). Never raise.
- **`reopen` uses `closed_at` (CR-037).** If `closed_at` is `None` (race condition or data error), treat as if window has elapsed and raise `CYCLE_005`.
- **`reporting_currency` (CR-023):** Validate 3-letter alpha on create; no conversion logic anywhere.

---

## 7. Verbatim Outputs

- `CYCLE_001` — "A non-closed cycle already exists for this fiscal year."
- `CYCLE_002` — "One or more filing units lack a manager. Assign managers or exclude the units."
- `CYCLE_003` — "Invalid cycle state transition."
- `CYCLE_004` — "Cycle is not open. Writes are not permitted." (raised by `assert_open`)
- `CYCLE_005` — "Reopen window has elapsed. Contact SystemAdmin."
- Empty cycle (no Open cycle) → dashboard returns sentinel `"尚未開放週期"` (produced by consolidation, not cycles).

---

## 8. Consistency Constraints

**CR-001 — Error code registry single source**
*"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
Codes raised: `CYCLE_001`, `CYCLE_002`, `CYCLE_003`, `CYCLE_004`, `CYCLE_005`.

**CR-005 — Cycle state assertion BEFORE write operations**
*"This service's first action is `await cycles.assert_open(cycle_id)`. Subsequent steps may assume the cycle is Open."*
This module PROVIDES `assert_open`. Consumed by M4, M5, M6. The method itself raises `CYCLE_004`.

**CR-006 — Audit AFTER commit, BEFORE return**
*"This service commits the DB transaction first, then calls `audit.record(...)`, then returns. If audit fails, the entire operation is rolled back (audit failure = cannot honor FR-023)."*
Applies to: `create`, `open`, `close`, `reopen`, `set_reminder_schedule`.

**CR-008 — Filing-unit list resolution before manager check (FR-002)**
*"`list_filing_units(cycle_id)` first enumerates ALL `org_units WHERE is_filing_unit = TRUE`, then LEFT JOINs to users to compute `has_manager`. The check returns `has_manager=False` rows so the caller can warn — it does NOT silently filter them out."*

**CR-010 — 0000公司 excluded from filing-unit operations**
*"This module never treats `org_units WHERE level_code = '0000'` as a filing unit. Use the `is_filing_unit = TRUE` filter consistently — do NOT filter by level_code."*

**CR-017 — Filing-unit lookup by `is_filing_unit` flag, NOT by `level_code` set**
*"All filing-unit queries use `WHERE is_filing_unit = TRUE`. The `level_code` is informational and may not always match the rule — `is_filing_unit` is the source of truth."*

**CR-023 — Currency code accepted but not converted**
*"`reporting_currency` is validated as a 3-letter ISO 4217 code on cycle create and stored as-is. NO conversion logic anywhere — sums use the raw amounts. Default `'TWD'`."*

**CR-026 — `unsubmitted_for_cycle` shared query**
*"Use `infra.db.repos.budget_uploads_query.unsubmitted_for_cycle(db, cycle_id)` for the unsubmitted-units query. Do not write a new SQL join."*
This module SHIPS `unsubmitted_for_cycle` in `infra/db/repos/budget_uploads_query.py`.

**CR-027 — `unsubmitted` excludes already-uploaded units**
*"`unsubmitted_for_cycle` returns filing units (`is_filing_unit = TRUE`) for the cycle that have ZERO rows in `budget_uploads` for that `(cycle_id, org_unit_id)`. Test with a unit that has 2 upload versions; the unit is NOT in the result set."*

**CR-028 — Email recipient computation: filing-unit manager + upline reviewer**
*"The recipient resolver walks `parent_id` from the source org unit until it finds an `OrgUnit` with at least one User holding `UplineReviewer` (or the FinanceAdmin role for global recipients). If no upline is found at the top of the tree, log `event=notification.no_upline_found` at WARN with the source org unit id; do not raise."*

**CR-035 — Cron callback exception isolation**
*"The cron callback wraps its body in `try/except Exception` at the outermost layer. On exception: `log.error('scheduler.callback_failed', ...)` and return — never re-raise."*

**CR-037 — Reopen window enforcement**
*"`reopen()` raises `CYCLE_005` if `(now_utc() - cycle.closed_at).days > BC_REOPEN_WINDOW_DAYS`. The check uses `closed_at` specifically — not `created_at` or `updated_at`."*

**CR-038 — Time zone for cron evaluation**
*"`infra.scheduler` configures APScheduler with `timezone=ZoneInfo(settings.timezone)`. The cron expression `0 9 * * *` is interpreted as 09:00 in Asia/Taipei, NOT UTC."*

---

## 9. Tests

### `test_service.py` (unit — `create`)

1. **`test_create_cycle_success`** — valid `fiscal_year=2026`, `deadline`, `currency='TWD'`; assert `BudgetCycle` returned with `status=draft`; audit entry created.
2. **`test_create_cycle_conflict_raises_cycle_001`** — seed an Open cycle for `fiscal_year=2026`; call `create(2026, ...)` again; assert `ConflictError(code='CYCLE_001')`.
3. **`test_create_cycle_allows_new_year_when_existing_is_closed`** — seed a Closed cycle for `2026`; create another for `2026`; assert succeeds (UNIQUE partial index allows it).

### `test_service.py` (unit — `open`)

1. **`test_open_cycle_success`** — Draft cycle, all filing units have managers; assert `status=open`, returns filing unit list excluding 0000.
2. **`test_open_cycle_wrong_state_raises_cycle_003`** — already Open cycle; call `open`; assert `CYCLE_003`.
3. **`test_open_cycle_missing_manager_raises_cycle_002`** — one filing unit with no User row; assert `CYCLE_002`.
4. **`test_open_cycle_excluded_unit_bypasses_manager_check`** — unit has no manager but is in `excluded_for_cycle_ids`; assert open succeeds, excluded unit not in returned filing units.

### `test_service.py` (unit — `reopen`)

1. **`test_reopen_within_window_succeeds`** — closed 3 days ago with `BC_REOPEN_WINDOW_DAYS=7`; assert `status=open`.
2. **`test_reopen_outside_window_raises_cycle_005`** — closed 8 days ago; assert `CYCLE_005`.
3. **`test_reopen_uses_closed_at_not_created_at`** — `closed_at` 8 days ago but `created_at` 2 days ago; assert `CYCLE_005` (uses `closed_at`).

### `test_filing_units.py` (unit)

1. **`test_resolve_filing_units_includes_no_manager_unit`** — filing unit with zero User rows; assert `has_manager=False` in result.
2. **`test_resolve_filing_units_excludes_non_filing_units`** — `0000` org unit with `is_filing_unit=FALSE`; assert not in result.
3. **`test_resolve_filing_units_honors_excluded_for_cycle`** — unit excluded for this cycle_id; assert `excluded=True`.

### `test_unsubmitted_query.py` (integration)

1. **`test_unsubmitted_excludes_uploaded_units`** — 3 units: A (0 uploads), B (1 upload), C (2 uploads); assert result = [A] only (CR-027).
2. **`test_unsubmitted_empty_when_all_uploaded`** — all units have uploads; assert empty list.

### `test_cycles.py` (API)

1. **`test_create_cycle_requires_finance_admin`** — POST as `FilingUnitManager`; assert 403.
2. **`test_open_cycle_returns_filing_units`** — POST open as `FinanceAdmin`; assert 200 with filing unit list.
3. **`test_patch_reminder_schedule_empty_disables`** — PATCH `days_before=[]`; assert 200; verify no schedules in DB.
4. **`test_patch_org_unit_excluded_for_cycle`** — PATCH `/admin/org-units/{id}` with `excluded_for_cycle_ids=[cycle_id]`; assert 200; filing unit marked excluded.
