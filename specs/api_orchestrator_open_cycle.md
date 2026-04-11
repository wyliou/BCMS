# Spec: api/v1/orchestrators/open_cycle (M11 orchestrator)

**Batch:** 6
**Complexity:** Complex

## 1. Module Paths & Test Paths

| File | Test |
|---|---|
| `backend/src/app/api/v1/orchestrators/open_cycle.py` | `backend/tests/api/test_open_cycle_pipeline.py` |

---

## 2. Functional Requirements

### FR-003 — Draft → Open Orchestration Pipeline

The open-cycle orchestrator is the single entry point for transitioning a cycle from Draft to Open. It enforces the exact 5-step pipeline sequence. **No step may be reordered.** The sequence is mandated by CR-004, CR-005, CR-006, CR-007 (inapplicable here), and CR-008.

| Step | Action | Module | CR |
|---|---|---|---|
| 1 | RBAC check | `core.security.RBAC` | CR-032 |
| 2 | `CycleService.open(cycle_id)` | `domain.cycles` | CR-005, CR-008 |
| 3 | `TemplateService.generate_for_cycle(cycle, filing_units, user)` | `domain.templates` | CR-009, CR-010 |
| 4 | `NotificationService.send_batch('cycle_opened', recipient_ids, context)` | `domain.notifications` | CR-003, CR-010 |
| 5 | Return `OpenCycleResponse` | — | — |

**Step 1 — RBAC:** Route declares `Depends(RBAC.require_role(Role.FinanceAdmin, Role.SystemAdmin))`. No other roles may open a cycle. Failure raises `RBAC_001` → 403.

**Step 2 — `CycleService.open(cycle_id)`:**
- Returns `(BudgetCycle, list[OrgUnit])`.
- `list[OrgUnit]` is the set of actionable filing units (already excludes `0000` and excluded units — CR-010).
- If cycle is not in Draft state, raises `CYCLE_003` → 409. Orchestrator does NOT catch this; propagates to global handler.
- If any non-excluded filing unit lacks a manager, raises `CYCLE_002` → 409. Propagates.

**Step 3 — `TemplateService.generate_for_cycle(cycle, filing_units, user)`:**
- Input: the `list[OrgUnit]` from Step 2.
- Returns `list[TemplateGenerationResult]` — one per filing unit with `status='generated'` or `status='generation_error'`.
- Per-unit failures are captured in the result; no exception propagates from this step unless the pre-loop `operational_codes` fetch fails (which would be an `InfraError` and propagates to global handler).
- The orchestrator passes `filing_units` directly; it does NOT filter by `is_filing_unit` or re-check `0000` exclusion (trusted from Step 2).

**Step 4 — `NotificationService.send_batch(NotificationTemplate.cycle_opened, recipient_ids, context)`:**
- `recipient_ids`: list of `user_id` values for managers of each actionable filing unit (derived from `filing_units[i].manager_user_id` if available, or resolved inline).
- If a filing unit has no manager user ID (unusual — Step 2 should have blocked this), log WARN and exclude from recipients. Do NOT raise.
- `context`: `{'fiscal_year': cycle.fiscal_year, 'deadline': str(cycle.deadline), 'cycle_id': str(cycle.id)}`.
- Returns `list[Notification]`.
- Notification send failures do NOT fail the open-cycle operation. If `send_batch` raises, catch `AppError`, log WARN, set `dispatch_summary.errors += 1`, continue.

**Step 5 — Return `OpenCycleResponse`:**
- HTTP 200 (the cycle was already transitioned in Step 2).
- Body: `OpenCycleResponse` with:
  - `cycle`: serialized `BudgetCycle`.
  - `generation_summary`: `{'total': int, 'generated': int, 'errors': int, 'error_details': list[{org_unit_id, error}]}`.
  - `dispatch_summary`: `{'total_recipients': int, 'sent': int, 'errors': int}`.

---

## 3. Exports

```python
# api/v1/orchestrators/open_cycle.py

async def open_cycle_endpoint(
    cycle_id: UUID,
    user: User = Depends(current_user),
    _rbac: None = Depends(RBAC.require_role(Role.FinanceAdmin, Role.SystemAdmin)),
    cycle_service: CycleService = Depends(get_cycle_service),
    template_service: TemplateService = Depends(get_template_service),
    notification_service: NotificationService = Depends(get_notification_service),
) -> OpenCycleResponse:
    """Execute the 5-step open-cycle pipeline.

    Step 1: RBAC enforced by Depends(RBAC.require_role(...)).
    Step 2: CycleService.open — transitions Draft→Open, returns filing units.
    Step 3: TemplateService.generate_for_cycle — per-unit template generation.
    Step 4: NotificationService.send_batch — cycle_opened emails to filing unit managers.
    Step 5: Return OpenCycleResponse with transition + generation + dispatch summaries.

    Args:
        cycle_id: UUID of the cycle to open (from path parameter).
        user: Authenticated user (FinanceAdmin or SystemAdmin).
        _rbac: RBAC dependency (raises RBAC_001 if role fails).
        cycle_service: Injected CycleService.
        template_service: Injected TemplateService.
        notification_service: Injected NotificationService.

    Returns:
        OpenCycleResponse: Cycle state + generation summary + dispatch summary.

    Raises:
        ForbiddenError(RBAC_001): Caller does not have required role.
        ConflictError(CYCLE_003): Cycle is not in Draft state.
        AppError(CYCLE_002): Non-excluded filing unit lacks a manager.
    """
```

**Pydantic schemas:**
```python
class GenerationSummary(BaseModel):
    total: int
    generated: int
    errors: int
    error_details: list[dict]  # [{'org_unit_id': str, 'error': str}]

class DispatchSummary(BaseModel):
    total_recipients: int
    sent: int
    errors: int

class OpenCycleResponse(BaseModel):
    cycle: BudgetCycleSchema
    generation_summary: GenerationSummary
    dispatch_summary: DispatchSummary
```

---

## 4. Imports

| Module | Symbols | Called by | Step |
|---|---|---|---|
| `domain.cycles` | `CycleService`, `CycleService.open` | orchestrator | Step 2 |
| `domain.templates` | `TemplateService`, `TemplateService.generate_for_cycle` | orchestrator | Step 3 |
| `domain.notifications` | `NotificationService`, `NotificationService.send_batch`, `NotificationTemplate` | orchestrator | Step 4 |
| `core.security` | `User`, `Role`, `RBAC`, `current_user` | route dependency | Step 1 |
| `app.deps` | `get_cycle_service`, `get_template_service`, `get_notification_service`, `current_user` | FastAPI Depends | Steps 1–4 |

### Required Call Order (MUST NOT be reordered)

```
Step 1: RBAC check (FastAPI Depends — happens before handler body executes)
Step 2: cycle, filing_units = await cycle_service.open(cycle_id)
Step 3: generation_results = await template_service.generate_for_cycle(cycle, filing_units, user)
Step 4: notifications = await notification_service.send_batch(
            NotificationTemplate.cycle_opened,
            recipient_ids=[...],
            context={...},
        )
Step 5: return OpenCycleResponse(...)
```

**Sequencing rationale:**
- Step 2 must precede Step 3: templates need the confirmed-Open cycle and the actionable filing unit list (CR-008 — list resolved inside `CycleService.open`).
- Step 2 must precede Step 4: notifications go out only after the cycle is confirmed Open.
- Step 3 must precede Step 4: generation is an idempotent operation that establishes the template state; notifications reference template download links. If generation partially fails, notifications still go out for successfully-generated units (the `generation_error` units get no notification — see Step 4 implementation note).
- Step 5 aggregates results from Steps 2–4 — must be last.

**Step 4 recipient derivation:**
```python
recipient_ids = []
for ou in filing_units:
    # Prefer manager from filing_unit info (has_manager=True means a user exists)
    managers = await db.execute(
        select(User.id).where(
            User.org_unit_id == ou.id,
            User.role.in_([Role.FilingUnitManager, Role.UplineReviewer])
        )
    )
    for uid in managers.scalars():
        recipient_ids.append(uid)
if not recipient_ids:
    log.warn("open_cycle.no_recipients_found", cycle_id=cycle_id)
```

**Step 4 error handling:**
```python
try:
    notifications = await notification_service.send_batch(
        NotificationTemplate.cycle_opened, recipient_ids, context
    )
    dispatch_summary = DispatchSummary(
        total_recipients=len(recipient_ids),
        sent=len([n for n in notifications if n.status == 'sent']),
        errors=len([n for n in notifications if n.status == 'failed']),
    )
except AppError as e:
    log.warn("open_cycle.notification_batch_failed", error=str(e))
    dispatch_summary = DispatchSummary(
        total_recipients=len(recipient_ids), sent=0, errors=len(recipient_ids)
    )
```

---

## 5. Side Effects

- Transitions `BudgetCycle.status` to `open` (via `CycleService.open`).
- Creates `ExcelTemplate` rows per filing unit (via `TemplateService.generate_for_cycle`).
- Saves workbook files to `infra.storage`.
- Creates `Notification` rows and sends `cycle_opened` emails.
- Writes `audit_logs` rows (within the called services — not in the orchestrator itself).

---

## 6. Gotchas

- **This is a THIN ORCHESTRATOR.** No business logic, no DB writes, no math. All logic lives in the three domain services. The orchestrator only sequences calls and assembles the response.
- **Step 2 errors (CYCLE_003, CYCLE_002) propagate without catch.** The orchestrator does NOT wrap Step 2 in try/except — these are fatal and should return 409.
- **Step 3 per-unit errors do NOT fail the endpoint.** `TemplateGenerationResult.status='generation_error'` is surfaced in `generation_summary.error_details`, not as an HTTP error.
- **Step 4 errors do NOT fail the endpoint.** The cycle is already Open after Step 2. A notification failure is non-fatal; it is surfaced in `dispatch_summary.errors`.
- **`NotificationTemplate.cycle_opened` must be a `NotificationTemplate` enum member (CR-003).** Never pass the string `'cycle_opened'` directly.
- **CR-010 — No 0000 in `filing_units`.** The `CycleService.open` already excludes `0000`. The orchestrator trusts this; it does NOT re-filter.
- **RBAC at the route (CR-032).** The `Depends(RBAC.require_role(...))` must be declared on the route, not inside the handler body.
- **`current_user` provides the authenticated user.** The `user` object is passed to both `template_service.generate_for_cycle` and as context for notifications. Do NOT re-fetch from DB.
- **Idempotency:** If a cycle is already Open and this endpoint is called again, `CycleService.open` raises `CYCLE_003`. This prevents accidental double-generation.

---

## 7. Verbatim Outputs

HTTP responses:
- `200 OK` with `OpenCycleResponse` on success.
- `403 Forbidden` with `error.code='RBAC_001'` if role check fails (Step 1).
- `409 Conflict` with `error.code='CYCLE_003'` if cycle is not Draft (Step 2).
- `409 Conflict` with `error.code='CYCLE_002'` if a filing unit lacks a manager (Step 2).

`OpenCycleResponse` example:
```json
{
  "cycle": {"id": "...", "status": "open", "fiscal_year": 2026, ...},
  "generation_summary": {
    "total": 12,
    "generated": 11,
    "errors": 1,
    "error_details": [{"org_unit_id": "...", "error": "storage timeout"}]
  },
  "dispatch_summary": {
    "total_recipients": 12,
    "sent": 12,
    "errors": 0
  }
}
```

---

## 8. Consistency Constraints

**CR-001 — Error code registry single source**
*"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
Codes propagated: `RBAC_001`, `CYCLE_002`, `CYCLE_003`.

**CR-003 — Notification template names single source**
*"All `notifications.send/send_batch` calls pass a member of `NotificationTemplate`; no string literals."*
This module calls `send_batch(NotificationTemplate.cycle_opened, ...)`.

**CR-005 — Cycle state assertion BEFORE write operations**
*"This service's first action is `await cycles.assert_open(cycle_id)`. Subsequent steps may assume the cycle is Open."*
In this orchestrator, `CycleService.open` (Step 2) performs the transition and all internal state checks. The orchestrator does not call `assert_open` separately.

**CR-006 — Audit AFTER commit, BEFORE return**
*"This service commits the DB transaction first, then calls `audit.record(...)`, then returns."*
Audit is written inside `CycleService.open` and `TemplateService.generate_for_cycle`. The orchestrator does not audit directly.

**CR-008 — Filing-unit list resolution before manager check**
*"`list_filing_units(cycle_id)` first enumerates ALL `org_units WHERE is_filing_unit = TRUE`, then LEFT JOINs to users to compute `has_manager`."*
`CycleService.open` (Step 2) owns this logic. The orchestrator trusts the returned `filing_units` list.

**CR-010 — 0000公司 excluded from filing-unit operations**
*"This module never treats `org_units WHERE level_code = '0000'` as a filing unit."*
The `filing_units` list from `CycleService.open` already excludes `0000`. The orchestrator does not re-check.

**CR-032 — RBAC scope matrix completeness**
*"This route declares `Depends(RBAC.require_role(...))` AND, where the URL contains a resource id, `Depends(RBAC.require_scope(resource_type, resource_id_param))`. Both must be present."*
Route: `Depends(RBAC.require_role(Role.FinanceAdmin, Role.SystemAdmin))` is declared. The `cycle_id` path param is additionally validated by `CycleService.open` (NotFoundError if missing).

---

## 9. Tests

### `test_open_cycle_pipeline.py` (API)

1. **`test_open_cycle_success_full_pipeline`** — `FinanceAdmin`, valid Draft cycle, all filing units have managers; assert 200, `generation_summary.generated > 0`, `dispatch_summary.sent > 0`, cycle `status='open'` in DB.
2. **`test_open_cycle_requires_finance_or_system_admin`** — POST as `FilingUnitManager`; assert 403, `error.code='RBAC_001'`.
3. **`test_open_cycle_non_draft_returns_cycle_003`** — cycle already Open; assert 409, `error.code='CYCLE_003'`.
4. **`test_open_cycle_missing_manager_returns_cycle_002`** — one filing unit has no manager user; assert 409, `error.code='CYCLE_002'`.
5. **`test_open_cycle_generation_failure_does_not_fail_endpoint`** — `infra.storage.save` raises for one unit; assert 200, `generation_summary.errors=1`, `generation_summary.generated=N-1`.
6. **`test_open_cycle_notification_failure_does_not_fail_endpoint`** — SMTP raises; assert 200, `dispatch_summary.errors > 0`, cycle still Open.
7. **`test_open_cycle_step_order_enforced`** — mock Step 2 to raise; assert Steps 3 and 4 were NOT called (verify via mock call counts).
