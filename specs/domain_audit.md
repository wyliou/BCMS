# Spec: domain/audit (Batch 1 — M9)

## Module Paths

| File | Path | Test Path |
|---|---|---|
| Actions enum | `backend/src/app/domain/audit/actions.py` | n/a (trivial enum) |
| ORM model | `backend/src/app/domain/audit/models.py` | n/a |
| Repository | `backend/src/app/domain/audit/repo.py` | `backend/tests/integration/audit/test_repo.py` |
| Service | `backend/src/app/domain/audit/service.py` | `backend/tests/unit/audit/test_service.py`, `backend/tests/integration/audit/test_service.py` |
| API routes | `backend/src/app/api/v1/audit.py` | `backend/tests/api/test_audit.py` |

---

## FRs

### FR-023 — Audit Log (P0)

- **Append-only table:** `audit_logs` with `sequence_no BIGSERIAL UNIQUE`; `UPDATE`/`DELETE` revoked at DB level (alembic_baseline migration applies `REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC`).
- **Hash chain integrity:** Each row stores `prev_hash BYTEA` (hash of the previous row) and `hash_chain_value BYTEA` (HMAC-SHA256(`BC_AUDIT_HMAC_KEY`, `prev_hash || serialized_payload`)). The very first row uses `prev_hash = b'\x00' * 32` (genesis sentinel).
- **`verify_chain(start, end)`:** Fetches rows in `sequence_no` order within the range, re-serializes each using `_serialize_for_chain`, recomputes `chain_hash(prev_hash, payload)`, and compares to stored `hash_chain_value`. Raises `AUDIT_001` on first mismatch.
- **Retention:** ≥5 years after cycle close. Enforced by offline retention job — schema preserves rows indefinitely.
- **Filterable query interface:** Filters by `user_id`, `action`, `resource_type`, `resource_type + resource_id`, `occurred_at` range; paginated.
- **Error handling:**
  - `AUDIT_001` (HTTP 500): hash chain verification failed.
  - `AUDIT_002` (HTTP 400): filter parameters invalid (e.g. malformed date range).
- **Routes:**
  - `GET /api/v1/audit-logs` — query with filters; returns paginated items.
  - `GET /api/v1/audit-logs/verify` — verify hash chain for a date range; returns `{ verified: true, range: [...], chain_length: N }`.
  - `GET /api/v1/audit-logs/export` — CSV export of filtered range (streamed response).
  - **Roles:** `ITSecurityAuditor` only for all three routes.

---

## Exports

### `actions.py`

```python
from enum import StrEnum

class AuditAction(StrEnum):
    """Single-source enum of every recordable audit event.

    This enum is the canonical owner of all audit action strings.
    All audit.record() calls must use a member of this enum — no string literals.
    """
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_AUTHORIZE_FAILED = "LOGIN_AUTHORIZE_FAILED"
    LOGOUT = "LOGOUT"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    RBAC_DENIED = "RBAC_DENIED"
    AUTH_FAILED = "AUTH_FAILED"
    CYCLE_OPEN = "CYCLE_OPEN"
    CYCLE_CLOSE = "CYCLE_CLOSE"
    CYCLE_REOPEN = "CYCLE_REOPEN"
    CYCLE_CREATE = "CYCLE_CREATE"
    TEMPLATE_DOWNLOAD = "TEMPLATE_DOWNLOAD"
    TEMPLATE_REGENERATE = "TEMPLATE_REGENERATE"
    BUDGET_UPLOAD = "BUDGET_UPLOAD"
    BUDGET_UPLOAD_FAILED = "BUDGET_UPLOAD_FAILED"
    PERSONNEL_IMPORT = "PERSONNEL_IMPORT"
    PERSONNEL_IMPORT_FAILED = "PERSONNEL_IMPORT_FAILED"
    SHARED_COST_IMPORT = "SHARED_COST_IMPORT"
    SHARED_COST_IMPORT_FAILED = "SHARED_COST_IMPORT_FAILED"
    ACTUALS_IMPORT = "ACTUALS_IMPORT"
    NOTIFY_SENT = "NOTIFY_SENT"
    NOTIFY_FAILED = "NOTIFY_FAILED"
    NOTIFY_RESENT = "NOTIFY_RESENT"
    RESUBMIT_REQUEST = "RESUBMIT_REQUEST"
    REPORT_EXPORT_QUEUED = "REPORT_EXPORT_QUEUED"
    REPORT_EXPORT_COMPLETE = "REPORT_EXPORT_COMPLETE"
    REPORT_EXPORT_FAILED = "REPORT_EXPORT_FAILED"
    CHAIN_VERIFIED = "CHAIN_VERIFIED"
    AUDIT_EXPORT = "AUDIT_EXPORT"
    USER_ROLE_UPDATED = "USER_ROLE_UPDATED"
    ORG_UNIT_CREATED = "ORG_UNIT_CREATED"
    ORG_UNIT_UPDATED = "ORG_UNIT_UPDATED"
```

### `models.py`

```python
class AuditLog(Base):
    """SQLAlchemy ORM for audit_logs table.

    Append-only. Never update or delete rows directly — ORM does not protect
    against this; the DB REVOKE and application conventions do.

    Columns mirror architecture §6 audit_logs DDL exactly.
    """
    __tablename__ = "audit_logs"

    id: Mapped[UUID]                          # UUID PK
    sequence_no: Mapped[int]                  # BIGSERIAL UNIQUE
    user_id: Mapped[UUID | None]              # FK users(id), nullable
    action: Mapped[str]                       # AuditAction string value
    resource_type: Mapped[str]                # e.g. "budget_upload", "cycle"
    resource_id: Mapped[UUID | None]
    ip_address: Mapped[str | None]            # INET stored as str
    details: Mapped[dict]                     # JSONB
    prev_hash: Mapped[bytes]                  # BYTEA
    hash_chain_value: Mapped[bytes]           # BYTEA
    occurred_at: Mapped[datetime]             # TIMESTAMPTZ UTC
```

### `repo.py`

```python
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

@dataclass
class AuditFilters:
    """Filter parameters for audit log queries.

    Attributes:
        user_id (UUID | None): Filter to a specific user.
        action (str | None): Filter to a specific AuditAction value.
        resource_type (str | None): Filter to a resource type.
        resource_id (UUID | None): Filter to a specific resource ID.
        from_dt (datetime | None): Start of occurred_at range (inclusive, UTC).
        to_dt (datetime | None): End of occurred_at range (inclusive, UTC).
        page (int): Page number, 1-based. Defaults to 1.
        size (int): Page size, max 200. Defaults to 50.
    """
    user_id: UUID | None = None
    action: str | None = None
    resource_type: str | None = None
    resource_id: UUID | None = None
    from_dt: datetime | None = None
    to_dt: datetime | None = None
    page: int = 1
    size: int = 50


@dataclass
class Page:
    """Paginated result wrapper.

    Attributes:
        items (list): Page items.
        total (int): Total matching rows.
        page (int): Current page number.
        size (int): Page size.
    """
    items: list
    total: int
    page: int
    size: int


class AuditRepo:
    """Data-access layer for audit_logs.

    Methods never write; write path lives exclusively in AuditService.record().
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an async session.

        Args:
            db (AsyncSession): Active async session.
        """

    async def fetch_page(self, filters: AuditFilters) -> Page:
        """Fetch a paginated, filtered page of audit log rows.

        Args:
            filters (AuditFilters): Query filters and pagination params.

        Returns:
            Page: Paginated audit log rows.

        Raises:
            AppError: code='AUDIT_002' if filter params are invalid (e.g. to_dt < from_dt).
        """

    async def fetch_range(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> list[AuditLog]:
        """Fetch all audit log rows in the given occurred_at range, ordered by sequence_no.

        Used by verify_chain and export. No pagination — returns all rows in range.

        Args:
            from_dt (datetime | None): Range start (inclusive). None = from beginning.
            to_dt (datetime | None): Range end (inclusive). None = through latest.

        Returns:
            list[AuditLog]: All rows in range, sorted by sequence_no ASC.
        """

    async def get_latest(self) -> AuditLog | None:
        """Return the audit log row with the highest sequence_no.

        Used by AuditService.record() to get prev_hash for the next row.

        Returns:
            AuditLog | None: Latest row, or None if table is empty.
        """
```

### `service.py`

```python
from datetime import datetime
from uuid import UUID
from app.domain.audit.actions import AuditAction
from app.domain.audit.models import AuditLog
from app.domain.audit.repo import AuditRepo, AuditFilters, Page

@dataclass
class ChainVerification:
    """Result of a hash chain verification.

    Attributes:
        verified (bool): True if all rows in range passed hash check.
        range_start (datetime | None): Start of verified range.
        range_end (datetime | None): End of verified range.
        chain_length (int): Number of rows checked.
        failed_at_sequence_no (int | None): sequence_no of first failed row, or None.
    """
    verified: bool
    range_start: datetime | None
    range_end: datetime | None
    chain_length: int
    failed_at_sequence_no: int | None


class AuditService:
    """Service for writing and querying the append-only audit log.

    Owns the hash chain advancement logic. Uses AuditRepo for read access.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize AuditService with an async DB session.

        Args:
            db (AsyncSession): Active async session.
        """

    async def record(
        self,
        action: AuditAction,
        resource_type: str,
        resource_id: UUID | None,
        user_id: UUID | None,
        ip_address: str | None,
        details: dict[str, object],
    ) -> AuditLog:
        """Append a new audit log entry with hash chain advancement.

        Steps:
        1. Fetch the latest row to get prev_hash (or b'\\x00'*32 for genesis).
        2. Serialize the new row payload via _serialize_for_chain.
        3. Compute hash_chain_value = chain_hash(prev_hash, serialized_payload).
        4. INSERT the new AuditLog row within the current session (does NOT commit;
           the calling service owns the commit).
        5. Return the new AuditLog row.

        Important: This method does NOT commit. It adds the ORM object to db's
        session. The calling service must commit AFTER calling this method and BEFORE
        returning to the caller (per CR-006: audit AFTER commit, BEFORE return).
        Wait — reread CR-006: "commit the DB transaction first, then calls audit.record".
        This means audit.record is called AFTER the owning service commits its main
        transaction. So audit.record inserts in a NEW transaction (or the same session
        but after the prior commit). The audit INSERT is then committed separately
        (or in the same commit if the session is still open).

        Clarification of sequencing: The CALLING service does:
        1. db.add(their_model); await db.commit()   # commit the main operation
        2. await audit_service.record(...)            # record the audit
        3. await db.commit()                          # commit the audit row
        4. return result

        This ensures the audit row is written to a committed state before the caller
        receives control. If audit.record() raises (e.g. chain hash conflict, DB error),
        the whole operation is treated as failed and the caller propagates the error.

        Args:
            action (AuditAction): The action being recorded.
            resource_type (str): Resource type string (e.g. 'budget_upload', 'cycle').
            resource_id (UUID | None): Resource UUID, or None for non-resource events.
            user_id (UUID | None): Acting user's ID; None for system/unauthenticated events.
            ip_address (str | None): Request IP address.
            details (dict[str, object]): Event-specific metadata (stored as JSONB).

        Returns:
            AuditLog: The newly inserted AuditLog ORM instance.

        Raises:
            InfraError: code='SYS_001' if the DB insert fails.
        """

    async def query(self, filters: AuditFilters) -> Page:
        """Return a filtered, paginated page of audit log rows.

        Args:
            filters (AuditFilters): Query filters including pagination.

        Returns:
            Page: Paginated audit log results.

        Raises:
            AppError: code='AUDIT_002' if filter params are invalid.
        """

    async def verify_chain(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> ChainVerification:
        """Re-compute hash chain for the given range and compare to stored values.

        Fetches rows in sequence_no order, re-serializes each with _serialize_for_chain,
        recomputes chain_hash(prev_hash, payload), and compares to stored hash_chain_value.

        Args:
            start (datetime | None): Start of range (occurred_at, inclusive). None = from first row.
            end (datetime | None): End of range (occurred_at, inclusive). None = through latest.

        Returns:
            ChainVerification: verified=True if all rows pass; verified=False + failed_at_sequence_no
                on first mismatch.

        Raises:
            AppError: code='AUDIT_001' if any row fails verification
                (raises rather than returning verified=False, per FR-023 strict mode).
        """

    @staticmethod
    def _serialize_for_chain(row: AuditLog) -> bytes:
        """Serialize an AuditLog row to bytes for hash chain computation.

        Uses JSON with sorted keys, no extra whitespace, UTC ISO-8601 datetimes.
        This MUST match the serialization used in both record() and verify_chain()
        exactly. Any drift breaks the chain.

        Args:
            row (AuditLog): The audit log row to serialize.

        Returns:
            bytes: UTF-8 JSON bytes with sorted keys and no extra whitespace.
        """
```

### `api/v1/audit.py`

```python
# Routes — thin orchestration only; all logic in AuditService

router = APIRouter(prefix="/audit-logs", tags=["audit"])

@router.get("", response_model=AuditLogsPage)
async def list_audit_logs(
    user_id: UUID | None = Query(None),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ITSecurityAuditor)),
) -> AuditLogsPage:
    """Query audit logs with optional filters and pagination.

    Args:
        user_id: Filter to specific user.
        action: Filter to specific AuditAction value.
        resource_type: Filter to resource type.
        from_: Start of occurred_at range (UTC).
        to: End of occurred_at range (UTC).
        page: Page number (1-based).
        size: Page size (max 200).
        db: Database session.
        _user: Authenticated ITSecurityAuditor user (RBAC enforced).

    Returns:
        AuditLogsPage: Paginated audit log items.
    """

@router.get("/verify", response_model=ChainVerificationResponse)
async def verify_audit_chain(
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_role(Role.ITSecurityAuditor)),
) -> ChainVerificationResponse:
    """Verify the audit log hash chain for a date range.

    Args:
        from_: Start of verification range (UTC).
        to: End of verification range (UTC).
        db: Database session.
        _user: Authenticated ITSecurityAuditor user.

    Returns:
        ChainVerificationResponse: Verification result with range and chain_length.

    Raises:
        AppError: code='AUDIT_001' (500) if any row fails verification.
    """

@router.get("/export")
async def export_audit_logs(
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(Role.ITSecurityAuditor)),
) -> StreamingResponse:
    """Export filtered audit log rows as a CSV file.

    Args:
        from_: Start of range.
        to: End of range.
        db: Database session.
        current_user: Authenticated ITSecurityAuditor user.

    Returns:
        StreamingResponse: CSV file download (Content-Disposition: attachment).
    """
```

---

## Imports

| Module | Symbols |
|---|---|
| `app.infra.db.session` | `get_session` |
| `app.infra.db.base` | `Base` |
| `app.infra.crypto` | `chain_hash` |
| `app.core.clock` | `now_utc` |
| `app.core.errors` | `AppError`, `InfraError` |
| `app.core.security.rbac` | `require_role`, `Role` — (Batch 2 dep; route file imports this at Batch 1+) |
| `sqlalchemy` | `select`, `func`, `and_` |
| `sqlalchemy.ext.asyncio` | `AsyncSession` |
| `sqlalchemy.orm` | `Mapped`, `mapped_column` |
| `uuid` | `UUID`, `uuid4` |
| `datetime` | `datetime`, `timezone` |
| `json` | `dumps` |
| `dataclasses` | `dataclass` |
| `fastapi` | `APIRouter`, `Query`, `Depends` |
| `fastapi.responses` | `StreamingResponse` |

---

## Side Effects

- `AuditService.record()` inserts one row to `audit_logs` per call.
- `AuditService.verify_chain()` is read-only; no writes.
- Route `/export` streams CSV bytes to the client.
- Every `AuditService.record()` call advances the hash chain: it reads the latest row (or genesis) and computes the new `hash_chain_value`.

---

## Hash Chain Payload Serialization (FR-023 / CR-031)

`_serialize_for_chain(row)` must produce the same bytes in both `record()` and `verify_chain()`. Use:

```python
import json

def _serialize_for_chain(row: AuditLog) -> bytes:
    payload = {
        "sequence_no": row.sequence_no,
        "user_id": str(row.user_id) if row.user_id else None,
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": str(row.resource_id) if row.resource_id else None,
        "ip_address": row.ip_address,
        "details": row.details,
        "occurred_at": row.occurred_at.isoformat(),  # must include +00:00 for UTC
    }
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode("utf-8")
```

Rules (verbatim from CR-031):
- JSON keys sorted.
- Separators `(',', ':')` (no extra spaces).
- Datetimes as ISO-8601 with UTC `+00:00` suffix (use `datetime.isoformat()` after ensuring `tzinfo=timezone.utc`).
- `verify_chain` uses the SAME helper — never duplicated.

---

## Verbatim Outputs (from architecture §5.11)

### GET `/api/v1/audit-logs` response shape:

```json
{
  "items": [
    {
      "id": "uuid",
      "timestamp": "2026-04-12T01:00:00+00:00",
      "user_id": "uuid",
      "action": "BUDGET_UPLOAD",
      "resource_type": "budget_upload",
      "resource_id": "uuid",
      "ip_address": "192.168.1.10",
      "details": {}
    }
  ],
  "total": 1234,
  "page": 1,
  "size": 50
}
```

### GET `/api/v1/audit-logs/verify` response shape:

```json
{
  "verified": true,
  "range": ["2026-01-01T00:00:00+00:00", "2026-04-12T00:00:00+00:00"],
  "chain_length": 5821
}
```

---

## Consistency Constraints

- **CR-001 Stage B check:** *"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
  - Raises `AUDIT_001` (chain broken), `AUDIT_002` (bad filters). Both in registry.

- **CR-002 Stage B check:** *"All `audit.record(...)` calls in this module use a member of `app.domain.audit.actions.AuditAction`; no string literals."*
  - `AuditAction` is defined in this module (`actions.py`). This module OWNS the enum. Verify that the export route records `AuditAction.AUDIT_EXPORT` and `AuditAction.CHAIN_VERIFIED` when those operations complete.

- **CR-006 Stage B check:** *"This service commits the DB transaction first, then calls `audit.record(...)`, then returns. If audit fails, the entire operation is rolled back (audit failure = cannot honor FR-023)."*
  - The audit service itself is the audit writer; its `record()` method is called BY other services after their own commit. Within the audit service's own write path (adding a new row), `record()` does not need to call itself — it IS the audit operation.

- **CR-031 Stage B check:** *"Audit row payload is serialized via the single private `_serialize_for_chain(row) -> bytes` helper. JSON keys sorted, separators `(',', ':')`, datetimes as ISO-8601 with UTC `+00:00`. `verify_chain` uses the same helper. NEVER duplicate the serialization logic."*

- **CR-033 Stage B check:** *"List endpoints call `await RBAC.scoped_org_units(user, db)` and pass the resulting set as a WHERE filter on `org_unit_id`. The query is run once per request; no caching across users."*
  - Audit logs are scoped by `ITSecurityAuditor` role only — all audit logs are visible to this role. There is no per-org-unit scope for audit. The `require_role(Role.ITSecurityAuditor)` dependency is the sole access control.

---

## Tests

### `actions.py`

1. `test_audit_action_is_str_enum` — `AuditAction.BUDGET_UPLOAD == "BUDGET_UPLOAD"`.
2. `test_all_actions_are_strings` — every member value is a non-empty uppercase string.
3. `test_no_duplicate_values` — all values are unique.

### `repo.py` (integration — requires Postgres)

4. `test_fetch_page_no_filters_returns_all` — insert 5 rows; `fetch_page(AuditFilters())` returns page with total=5.
5. `test_fetch_page_filter_by_action` — insert rows with mixed actions; filter returns only matching.
6. `test_fetch_page_filter_by_date_range` — rows with different `occurred_at`; filter by range returns correct subset.
7. `test_fetch_page_filter_invalid_range_raises_audit_002` — `to_dt < from_dt`; assert `AppError("AUDIT_002", ...)`.
8. `test_fetch_range_ordered_by_sequence_no` — 10 rows; result is in ascending `sequence_no` order.
9. `test_get_latest_returns_highest_sequence_no` — insert 3 rows; `get_latest()` returns row with max `sequence_no`.
10. `test_get_latest_empty_table_returns_none` — empty table; `get_latest()` returns `None`.

### `service.py` (unit tests — no DB)

11. `test_record_computes_chain_hash` — mock repo to return a previous row with known hash; assert new row's `hash_chain_value` matches expected `chain_hash(prev, payload)`.
12. `test_record_genesis_uses_zero_prev_hash` — mock repo to return `None`; assert `prev_hash == b'\x00' * 32`.
13. `test_serialize_for_chain_sorted_keys` — call `_serialize_for_chain`; parse JSON; assert keys are alphabetically sorted.
14. `test_serialize_for_chain_iso_utc_datetime` — `occurred_at` with `timezone.utc`; serialized string contains `+00:00`.
15. `test_verify_chain_success` — mock repo returning 3 real rows; recompute chain; assert `ChainVerification.verified == True`.
16. `test_verify_chain_tampered_row_raises_audit_001` — mock repo returning 3 rows; tamper one row's `details`; assert `AppError("AUDIT_001", ...)`.
17. `test_query_delegates_to_repo` — mock repo `fetch_page`; assert `query(filters)` returns repo result.

### `service.py` (integration — requires Postgres)

18. `test_record_inserts_row_to_db` — call `record(AuditAction.BUDGET_UPLOAD, ...)`, commit; assert row exists with correct `action`, `hash_chain_value`.
19. `test_verify_chain_100_rows` — insert 100 rows via `record()`; call `verify_chain(None, None)`; assert `verified == True, chain_length == 100`.
20. `test_verify_chain_tampered_db_row_raises` — insert 10 rows, manually UPDATE one row's `details` using raw SQL (bypassing the app layer REVOKE, since tests run as a superuser); assert `verify_chain` raises `AUDIT_001`.

### `api/v1/audit.py`

21. `test_list_audit_logs_rbac_requires_it_security_auditor` — request as `FinanceAdmin`; assert 403.
22. `test_list_audit_logs_returns_paginated_response` — as `ITSecurityAuditor`; assert 200, response has `items`, `total`, `page`, `size`.
23. `test_verify_chain_returns_verified_true` — seed rows with proper chain; assert 200, `verified == true`.
24. `test_verify_chain_broken_chain_returns_500_audit_001` — tamper a row; assert 500, `code == "AUDIT_001"`.
25. `test_export_returns_csv_content_disposition` — as `ITSecurityAuditor`; assert 200, `Content-Disposition: attachment; filename=audit_logs.csv`.
