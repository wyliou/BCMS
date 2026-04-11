# Spec: domain/notifications (M8)

**Batch:** 2
**Complexity:** Moderate

## 1. Module Paths & Test Paths

| File | Test |
|---|---|
| `backend/src/app/domain/notifications/service.py` | `backend/tests/unit/notifications/test_service.py`, `backend/tests/integration/notifications/test_service.py` |
| `backend/src/app/domain/notifications/resubmit.py` | `backend/tests/unit/notifications/test_resubmit.py` |
| `backend/src/app/domain/notifications/templates/cycle_opened.txt` | golden file test |
| `backend/src/app/domain/notifications/templates/upload_confirmed.txt` | golden file test |
| `backend/src/app/domain/notifications/templates/resubmit_requested.txt` | golden file test |
| `backend/src/app/domain/notifications/templates/deadline_reminder.txt` | golden file test |
| `backend/src/app/domain/notifications/templates/personnel_imported.txt` | golden file test |
| `backend/src/app/domain/notifications/templates/shared_cost_imported.txt` | golden file test |
| `backend/src/app/domain/notifications/models.py` | n/a |
| `backend/src/app/api/v1/notifications.py` | `backend/tests/api/test_notifications.py` |

---

## 2. Functional Requirements

### FR-013 — Upload Confirmation Notification

- **Trigger:** Called by `domain/budget_uploads.BudgetUploadService.upload` after a successful upload commit.
- **Recipients:** Uploader (by `user_id`) AND direct upline manager of the uploading org unit.
  - "Direct upline manager" resolution: walk `org_units.parent_id` from the upload's `org_unit_id` until an `OrgUnit` is found that has at least one `User` with role `UplineReviewer` (or `FinanceAdmin` as global fallback). If the entire chain has no manager, log `WARN event=notification.no_upline_found` with `org_unit_id` and continue — do NOT raise.
  - Contract note: the `cycles/filing_units` helper (Batch 4) will expose a `get_upline_manager(org_unit_id)` method. In Batch 2 the recipient resolver is implemented inline in `notifications/service.py` (same logic, private method `_resolve_upline_manager`). Batch 4 will not change the API surface.
- **Template:** `NotificationTemplate.upload_confirmed`
- **Context keys:** `version` (int), `filename` (str), `org_unit_name` (str), `cycle_fiscal_year` (int).
- **Failure semantics (CR-029):** Notification failure does NOT invalidate the upload. If `infra.email.send` raises, catch `NOTIFY_001`, mark the `Notification` row `status=failed`, log WARN, return the `Notification` to the caller. The upload service ignores the returned failed state and returns the upload as successful.

### FR-018 — Resubmit Request Notification

- **Trigger:** `FinanceAdmin` or `UplineReviewer` calls `POST /api/v1/notifications/resubmit`.
- **Recipients:** The manager(s) of the target `org_unit_id`.
- **Template:** `NotificationTemplate.resubmit_requested`
- **Context keys:** `reason` (str), `requester_name` (str), `target_unit_name` (str), `template_download_link` (str — included verbatim from context; link construction is caller's responsibility), `target_version` (int | None).

### FR-019 — Resubmit Record Before Send (LOCKED)

- **Decision locked:** `record → commit → send`. The sequence is non-negotiable.
- On `ResubmitRequestService.create`:
  1. Write `resubmit_requests` row.
  2. `await db.commit()`.
  3. Call `NotificationService.send(...)`.
  4. If step 1/2 fails → raise `NOTIFY_002`, do NOT send email.
  5. If step 3 fails → the resubmit record already exists; mark notification `failed` (CR-029 pattern), log WARN, return the `ResubmitRequest` (it is valid even if email failed).
- **Fields stored:** `cycle_id`, `org_unit_id`, `requester_id`, `reason`, `requested_at`, `target_version` (nullable), `notification_id` (FK to `notifications` table, may be null if email failed).

### FR-020 — Deadline Reminder Dispatch

- **Trigger:** Daily cron at 09:00 server TZ (APScheduler, Batch 4 cycles module owns the cron registration). `NotificationService.send_batch` is called by `CycleService.dispatch_deadline_reminders` (Batch 4).
- **Template:** `NotificationTemplate.deadline_reminder`
- **Recipients:** Filing-unit manager of each unsubmitted unit; cc upline reviewer (passed as separate `recipient_ids` in context, not as actual cc in `send_batch` — the email template renders both names in the body).
- **Context keys:** `cycle_deadline` (date ISO string), `org_unit_name` (str), `days_remaining` (int).

### FR-026 — Personnel Import Notification

- **Trigger:** Called by `PersonnelImportService.import_` (Batch 5) after successful commit.
- **Recipients:** All users with role `FinanceAdmin`.
- **Template:** `NotificationTemplate.personnel_imported`
- **Context keys:** `cycle_id` (UUID str), `version` (int), `uploader_name` (str).

### FR-029 — Shared Cost Import Notification

- **Trigger:** Called by `SharedCostImportService.import_` (Batch 5) after successful commit.
- **Recipients:** Manager of each `org_unit_id` in `diff_affected_units` result.
- **Template:** `NotificationTemplate.shared_cost_imported`
- **Context keys:** `cycle_id` (UUID str), `version` (int), `amount_delta` (str — Decimal formatted as string, CR-036).

---

## 3. Exports

```python
# domain/notifications/service.py

class NotificationTemplate(StrEnum):
    """Single source of truth for all notification template names (CR-003).

    Members must match filenames under domain/notifications/templates/*.txt.
    """
    cycle_opened = "cycle_opened"
    upload_confirmed = "upload_confirmed"
    resubmit_requested = "resubmit_requested"
    deadline_reminder = "deadline_reminder"
    personnel_imported = "personnel_imported"
    shared_cost_imported = "shared_cost_imported"

async def send(
    template: NotificationTemplate,
    recipient_id: UUID,
    context: dict,
    related: tuple[str, UUID] | None = None,
) -> Notification:
    """Send a single notification email using a named template.

    Args:
        template: NotificationTemplate enum member selecting the Jinja template file.
        recipient_id: User UUID; email resolved from users table.
        context: Template rendering context dict.
        related: Optional (resource_type, resource_id) tuple for the notifications row.

    Returns:
        Notification: Persisted notification row (status may be 'failed' on SMTP error).

    Raises:
        NotFoundError: recipient_id not found in users table.
    """

async def send_batch(
    template: NotificationTemplate,
    recipient_ids: list[UUID],
    context: dict,
    related: tuple[str, UUID] | None = None,
) -> list[Notification]:
    """Send the same notification to multiple recipients.

    Args:
        template: NotificationTemplate enum member.
        recipient_ids: List of User UUIDs.
        context: Shared template context (same for all recipients).
        related: Optional related resource tuple.

    Returns:
        list[Notification]: One Notification row per recipient.
    """

async def list_failed(limit: int = 100) -> list[Notification]:
    """Return failed notification rows ordered by created_at desc.

    Args:
        limit: Maximum number of rows to return.

    Returns:
        list[Notification]: Failed notification rows.
    """

async def resend(notification_id: UUID) -> Notification:
    """Retry sending a previously failed notification.

    Args:
        notification_id: UUID of the failed Notification row.

    Returns:
        Notification: Updated notification row.

    Raises:
        NotFoundError: notification_id not found.
        AppError(NOTIFY_001): Email send failed again; row re-marked failed.
    """

# domain/notifications/resubmit.py

async def create(
    cycle_id: UUID,
    org_unit_id: UUID,
    requester_id: UUID,
    reason: str,
    target_version: int | None = None,
) -> ResubmitRequest:
    """Create a resubmit request record then send notification email.

    Record is committed before email is attempted. On record failure raises
    NOTIFY_002 and no email is sent. On email failure, record remains valid.

    Args:
        cycle_id: Target cycle UUID.
        org_unit_id: Target org unit UUID.
        requester_id: User UUID of the requester.
        reason: Explanation provided by the requester.
        target_version: Optional specific upload version to re-submit.

    Returns:
        ResubmitRequest: Persisted resubmit request row.

    Raises:
        AppError(NOTIFY_002): DB write failed; no email sent.
    """

async def list(cycle_id: UUID, org_unit_id: UUID) -> list[ResubmitRequest]:
    """List all resubmit requests for a cycle/org unit pair.

    Args:
        cycle_id: Cycle UUID.
        org_unit_id: Org unit UUID.

    Returns:
        list[ResubmitRequest]: Ordered by requested_at desc.
    """
```

---

## 4. Imports

| Module | Symbols | Called by |
|---|---|---|
| `infra.email` | `EmailClient.send` | `NotificationService.send` and `send_batch` |
| `infra.db` | `get_session`, `AsyncSession` | All service methods |
| `core.clock` | `now_utc` | `Notification.created_at`, `ResubmitRequest.requested_at` |
| `domain.audit` | `AuditService.record`, `AuditAction` | After commit of each notification send (`AuditAction.NOTIFY_SENT`) |
| `core.security` | `User`, `Role` | Recipient lookup, requester validation |
| `core.errors` | `AppError`, `NotFoundError`, `InfraError` | Error raising; `NOTIFY_001`, `NOTIFY_002` from ERROR_REGISTRY |

### Required Call Order in `ResubmitRequestService.create` (CR-007)

1. Validate `requester` has role `FinanceAdmin` or `UplineReviewer`.
2. Begin DB transaction.
3. Insert `resubmit_requests` row.
4. `await db.commit()` — if this raises, raise `AppError(NOTIFY_002)` and return without calling email.
5. Call `NotificationService.send(NotificationTemplate.resubmit_requested, ...)`.
6. If step 5 raises `NOTIFY_001`: catch it, mark `Notification.status = failed`, log `WARN event=notification.send_failed`, return `ResubmitRequest`.
7. `await audit.record(AuditAction.RESUBMIT_REQUEST, ...)` — after commit (CR-006).
8. Return `ResubmitRequest`.

**Rationale:** Step 4 before step 5 is the CR-007 lock. Step 7 follows step 4 per CR-006.

---

## 5. Side Effects

- Writes `notifications` table row for every `send` / `send_batch` call (status `sent` or `failed`).
- Writes `resubmit_requests` table row on `ResubmitRequestService.create`.
- Sends SMTP email via `infra.email.EmailClient`.
- Writes `audit_logs` row after each successful notification commit.

---

## 6. Gotchas

- **`NotificationTemplate` is the single source of truth for template names (CR-003).** All callers in `domain/cycles`, `domain/budget_uploads`, `domain/personnel`, `domain/shared_costs` MUST import and pass `NotificationTemplate` members — no string literals.
- **Template files must exist** for every `NotificationTemplate` member. The build's final-gate check cross-references the enum against `*.txt` files in the templates directory.
- **`send` must never raise on SMTP failure** (except for lookup failures). SMTP errors are caught, the `Notification` row is set to `failed`, and the service returns normally. This is intentional — callers (upload services) rely on this behavior.
- **`ResubmitRequestService.create` is the ONE exception** where a DB failure must propagate as `NOTIFY_002` (CR-007). This is distinct from the CR-029 SMTP-failure pattern.
- **Recipient resolution** for `upload_confirmed` walks the org tree at call time (no cache). If no upline manager found, emit WARN and continue — do not raise.
- **`deadline_reminder` template** is used by `CycleService.dispatch_deadline_reminders` (Batch 4). The template must be available in Batch 2 even though the cron caller ships later.
- **`send_batch` is not atomic** — each recipient is attempted individually. Partial failures result in a mixed list of `sent` and `failed` rows. Callers must not assume all-or-nothing.

---

## 7. Verbatim Outputs (from PRD §4.7)

- FR-019 error on record write failure: raises `NOTIFY_002` (message template in ERROR_REGISTRY — "紀錄寫入失敗，通知未發送").
- FR-013: notification failure logged in audit and flagged in Dashboard as "通知未送達" (this is a UI string; backend sets `Notification.status = 'failed'`).

---

## 8. Consistency Constraints

**CR-001 — Error code registry single source**
*"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
Applies to: `NOTIFY_001`, `NOTIFY_002`.

**CR-002 — Audit action enum single source**
*"All `audit.record(...)` calls in this module use a member of `app.domain.audit.actions.AuditAction`; no string literals."*
Applies to: `NOTIFY_SENT`, `RESUBMIT_REQUEST`.

**CR-003 — Notification template names single source (OWNER)**
*"All `notifications.send/send_batch` calls pass a member of `NotificationTemplate`; no string literals."*
This module OWNS `NotificationTemplate`. Every caller must import from here. Template files under `domain/notifications/templates/` must have filenames matching enum values exactly (e.g., `upload_confirmed.txt`).

**CR-006 — Audit AFTER commit, BEFORE return**
*"This service commits the DB transaction first, then calls `audit.record(...)`, then returns. If audit fails, the entire operation is rolled back (audit failure = cannot honor FR-023)."*
Applies to: `ResubmitRequestService.create`.

**CR-007 — Resubmit record BEFORE notification send (FR-019)**
*"`ResubmitRequestService.create` writes the resubmit_requests row in a transaction; only after successful commit does it call `NotificationService.send`. Row-write failure raises `NOTIFY_002` and no email goes out."*

**CR-028 — Email recipient computation: filing-unit manager + upline reviewer (FR-013, FR-020)**
*"The recipient resolver walks `parent_id` from the source org unit until it finds an `OrgUnit` with at least one User holding `UplineReviewer` (or the FinanceAdmin role for global recipients). If no upline is found at the top of the tree, log `event=notification.no_upline_found` at WARN with the source org unit id; do not raise."*

**CR-029 — Notification failure does NOT invalidate upload (FR-013)**
*"The upload service commits the upload in transaction T1, then calls `notifications.send` in a separate transaction. If `send` raises (SMTP down, etc.), catch the `NOTIFY_001` exception, mark the notification row `failed`, log WARN, and return the successful `BudgetUpload` to the caller. The upload remains valid."*
Applies to: `NotificationService.send` — must not raise on SMTP failure; sets `status=failed` instead.

---

## 9. Tests

### `test_service.py` (unit — uses `infra.email.fake_smtp`)

1. **`test_send_success`** — call `send` with valid `recipient_id`; assert `Notification` row created with `status=sent`; `fake_smtp` records one outgoing message; `NOTIFY_SENT` audit entry written after commit.
2. **`test_send_smtp_failure_does_not_raise`** — configure `fake_smtp` to error; call `send`; assert NO exception raised; returned `Notification` has `status=failed`; WARN logged.
3. **`test_send_batch_partial_failure`** — two recipients, second SMTP call fails; assert two `Notification` rows, first `sent`, second `failed`; no exception raised to caller.
4. **`test_resend_failed_notification`** — insert `Notification(status=failed)`; call `resend`; configure `fake_smtp` to succeed; assert `status=sent`.
5. **`test_list_failed_returns_only_failed`** — insert one `sent` and two `failed` rows; assert `list_failed` returns exactly two.

### `test_resubmit.py` (unit)

1. **`test_create_resubmit_success`** — happy path: `ResubmitRequest` row created, email sent, `RESUBMIT_REQUEST` audit entry written.
2. **`test_create_resubmit_db_failure_raises_notify_002_no_email`** — inject DB error on insert; assert `AppError(NOTIFY_002)` raised; `fake_smtp` call count = 0.
3. **`test_create_resubmit_email_failure_record_valid`** — DB succeeds but SMTP fails; assert `ResubmitRequest` returned (not raised), `Notification.status=failed`.
4. **`test_list_resubmit_requests`** — insert 3 rows for same (cycle, org_unit); assert all 3 returned, ordered by `requested_at` desc.

### `test_notifications.py` (API)

1. **`test_list_failed_requires_finance_admin`** — GET as `FilingUnitManager`; assert 403.
2. **`test_list_failed_as_finance_admin`** — GET as `FinanceAdmin`; assert 200 list.
3. **`test_resend_notification`** — POST `/api/v1/notifications/{id}/resend`; assert 200 and `status=sent`.
4. **`test_create_resubmit_request`** — POST `/api/v1/notifications/resubmit`; assert 201 with `ResubmitRequest` payload.
5. **`test_create_resubmit_invalid_requester_role`** — POST as `FilingUnitManager`; assert 403.
