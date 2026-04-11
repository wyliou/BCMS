# Spec: api/v1/router + app/deps + schemas (M11 API surface)

**Batch:** 6
**Complexity:** Moderate

## 1. Module Paths & Test Paths

| File | Test |
|---|---|
| `backend/src/app/api/v1/router.py` | `backend/tests/api/test_router.py` |
| `backend/src/app/deps.py` | `backend/tests/api/test_deps.py` |
| `backend/src/app/schemas/cycles.py` | `backend/tests/unit/schemas/test_cycles.py` |
| `backend/src/app/schemas/templates.py` | `backend/tests/unit/schemas/test_templates.py` |
| `backend/src/app/schemas/budget_uploads.py` | `backend/tests/unit/schemas/test_budget_uploads.py` |
| `backend/src/app/schemas/personnel.py` | `backend/tests/unit/schemas/test_personnel.py` |
| `backend/src/app/schemas/shared_costs.py` | `backend/tests/unit/schemas/test_shared_costs.py` |
| `backend/src/app/schemas/consolidation.py` | `backend/tests/unit/schemas/test_consolidation.py` |
| `backend/src/app/schemas/notifications.py` | (covered by existing notification tests) |
| `backend/src/app/schemas/auth.py` | (covered by existing auth tests) |
| `backend/src/app/schemas/accounts.py` | (covered by existing account tests) |
| `backend/src/app/schemas/audit.py` | (covered by existing audit tests) |

---

## 2. Functional Requirements

### Router Aggregation

`app/api/v1/router.py` is a thin assembly file. It imports and includes all sub-routers under the `/api/v1` prefix. No business logic. Each sub-router is an `APIRouter` instance defined in its respective `api/v1/*.py` file.

**Sub-routers to include:**

| Router | Module | Prefix | Tags |
|---|---|---|---|
| `auth_router` | `api.v1.auth` | `/auth` | `["auth"]` |
| `cycles_router` | `api.v1.cycles` | `/cycles` | `["cycles"]` |
| `templates_router` | `api.v1.templates` | `/templates` | `["templates"]` |
| `budget_uploads_router` | `api.v1.budget_uploads` | `/budget-uploads` | `["budget-uploads"]` |
| `personnel_router` | `api.v1.personnel` | `/personnel` | `["personnel"]` |
| `shared_costs_router` | `api.v1.shared_costs` | `/shared-costs` | `["shared-costs"]` |
| `dashboard_router` | `api.v1.dashboard` | `/dashboard` | `["dashboard"]` |
| `reports_router` | `api.v1.reports` | `/reports` | `["reports"]` |
| `notifications_router` | `api.v1.notifications` | `/notifications` | `["notifications"]` |
| `audit_router` | `api.v1.audit` | `/audit` | `["audit"]` |
| `admin_router` | `api.v1.admin` | `/admin` | `["admin"]` |
| `open_cycle_router` | `api.v1.orchestrators.open_cycle` | `/orchestrators` | `["orchestrators"]` |

`main.py` mounts the top-level `v1_router` at `/api/v1`.

### `app/deps.py` — Dependency Providers

All FastAPI `Depends` factories used by route handlers. Each factory is `async def` and yields or returns the appropriate dependency.

| Provider | Signature | Purpose |
|---|---|---|
| `get_session` | `() -> AsyncIterator[AsyncSession]` | DB session (already in `infra.db.session`; re-exported here for convenience) |
| `current_user` | `(request: Request, db: AsyncSession = Depends(get_session)) -> User` | Validates `bc_session` JWT cookie; raises `AUTH_001` if invalid/expired |
| `get_audit_service` | `(db: AsyncSession = Depends(get_session)) -> AuditService` | AuditService factory |
| `get_cycle_service` | `(db: AsyncSession = Depends(get_session), audit: AuditService = Depends(get_audit_service)) -> CycleService` | CycleService factory |
| `get_template_service` | `(db, audit, cycle_svc, account_svc) -> TemplateService` | TemplateService factory |
| `get_budget_upload_service` | `(db, audit, cycle_svc, account_svc, notification_svc) -> BudgetUploadService` | BudgetUploadService factory |
| `get_personnel_service` | `(db, audit, cycle_svc, account_svc, notification_svc) -> PersonnelImportService` | PersonnelImportService factory |
| `get_shared_cost_service` | `(db, audit, cycle_svc, account_svc, notification_svc) -> SharedCostImportService` | SharedCostImportService factory |
| `get_notification_service` | `(db, audit) -> NotificationService` | NotificationService factory |
| `get_dashboard_service` | `(db, budget_svc) -> DashboardService` | DashboardService factory |
| `get_report_service` | `(db, budget_svc, personnel_svc, shared_cost_svc, account_svc) -> ConsolidatedReportService` | ConsolidatedReportService factory |
| `get_export_service` | `(db, report_svc, notification_svc) -> ConsolidatedExportService` | Export service factory |
| `get_account_service` | `(db, audit) -> AccountService` | AccountService factory |
| `csrf_dep` | `(request: Request) -> None` | Validates `X-CSRF-Token` header against `bc_csrf` cookie; raises `AUTH_002` if mismatch. Applied to all state-changing (POST/PATCH/DELETE) routes. |
| `get_org_unit_map` | `(db: AsyncSession = Depends(get_session)) -> dict[str, UUID]` | Per-request `org_unit_code_to_id_map` cache (wraps `_shared.queries`) |

### Schemas

Each schema file follows Pydantic v2 conventions. All ORM schemas use `model_config = ConfigDict(from_attributes=True)`. All `Decimal` fields use `model_config = ConfigDict(json_encoders={Decimal: str})`.

#### `schemas/cycles.py`

```python
class BudgetCycleCreate(BaseModel):
    fiscal_year: int
    deadline: date
    reporting_currency: str = "TWD"

class BudgetCycleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    fiscal_year: int
    deadline: date
    reporting_currency: str
    status: CycleStatus
    opened_at: datetime | None
    closed_at: datetime | None
    created_at: datetime

class ReminderScheduleUpdate(BaseModel):
    days_before: list[int]

class FilingUnitInfoSchema(BaseModel):
    org_unit_id: UUID
    code: str
    name: str
    has_manager: bool
    excluded: bool
    warnings: list[str]
```

#### `schemas/templates.py`

```python
class TemplateGenerationResultSchema(BaseModel):
    org_unit_id: UUID
    status: Literal["generated", "generation_error"]
    error: str | None = None

class TemplateDownloadResponse(BaseModel):
    filename: str
    content_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
```

#### `schemas/budget_uploads.py`

```python
class BudgetUploadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    cycle_id: UUID
    org_unit_id: UUID
    version: int
    filename: str
    file_hash: str
    uploader_id: UUID
    uploaded_at: datetime

class BudgetUploadListResponse(BaseModel):
    items: list[BudgetUploadSchema]
    total: int
```

#### `schemas/personnel.py`

```python
class PersonnelBudgetUploadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    cycle_id: UUID
    version: int
    filename: str
    uploader_id: UUID
    uploaded_at: datetime
    affected_org_units_summary: list[dict]

class PersonnelImportResponse(BaseModel):
    upload: PersonnelBudgetUploadSchema
    row_count: int
```

#### `schemas/shared_costs.py`

```python
class SharedCostUploadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    cycle_id: UUID
    version: int
    filename: str
    uploader_id: UUID
    uploaded_at: datetime
    affected_org_units_summary: list[dict]

class SharedCostImportResponse(BaseModel):
    upload: SharedCostUploadSchema
    row_count: int
    affected_unit_count: int
```

#### `schemas/consolidation.py`

```python
class DashboardItemSchema(BaseModel):
    org_unit_id: UUID
    org_unit_name: str
    status: Literal["not_downloaded", "downloaded", "uploaded", "resubmit_requested"]
    last_uploaded_at: datetime | None
    version: int | None

class DashboardResponseSchema(BaseModel):
    items: list[DashboardItemSchema]
    sentinel: str | None = None
    stale: bool = False
    summary: dict | None = None

class ConsolidatedReportRowSchema(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: str})
    org_unit_id: UUID
    org_unit_name: str
    account_code: str
    account_name: str
    actual: Decimal | None
    operational_budget: Decimal | None
    personnel_budget: Decimal | None
    shared_cost: Decimal | None
    delta_amount: Decimal | None
    delta_pct: str   # '9.1', 'N/A' — always a string, never null
    budget_status: Literal["not_uploaded", "uploaded"]

class ConsolidatedReportSchema(BaseModel):
    cycle_id: UUID
    rows: list[ConsolidatedReportRowSchema]
    budget_last_updated_at: datetime | None
    personnel_last_updated_at: datetime | None
    shared_cost_last_updated_at: datetime | None

class ExportRequestSchema(BaseModel):
    format: Literal["xlsx"] = "xlsx"

class ExportResultSchema(BaseModel):
    sync: bool
    file_url: str | None = None
    expires_at: datetime | None = None
    job_id: UUID | None = None
```

---

## 3. Exports

```python
# api/v1/router.py

from fastapi import APIRouter

v1_router = APIRouter()
# includes all sub-routers listed above

# app/deps.py

async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async SQLAlchemy session for the current request.

    Returns:
        AsyncIterator[AsyncSession]: Session committed/rolled back on context exit.
    """

async def current_user(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> User:
    """Extract and validate the authenticated user from the bc_session cookie.

    Args:
        request: Incoming FastAPI request.
        db: Async DB session for session lookup.

    Returns:
        User: Authenticated user ORM row.

    Raises:
        UnauthenticatedError(AUTH_001): Cookie missing, JWT invalid, or session expired.
    """

async def csrf_dep(request: Request) -> None:
    """Validate the CSRF double-submit cookie pattern.

    Compares X-CSRF-Token header against the bc_csrf cookie value.
    Applied to all state-mutating routes (POST, PATCH, DELETE).

    Args:
        request: Incoming FastAPI request.

    Raises:
        UnauthenticatedError(AUTH_002): CSRF token mismatch or missing.
    """
```

---

## 4. Imports

| Module | Symbols | Used in |
|---|---|---|
| `core.security` | `AuthService.current_user`, `RBAC`, `Role`, `User` | `deps.current_user`, route handlers |
| `infra.db.session` | `get_session` (re-exported) | `deps.get_session` |
| `domain.audit` | `AuditService` | `deps.get_audit_service` |
| `domain.cycles` | `CycleService` | `deps.get_cycle_service` |
| `domain.templates` | `TemplateService` | `deps.get_template_service` |
| `domain.budget_uploads` | `BudgetUploadService` | `deps.get_budget_upload_service` |
| `domain.personnel` | `PersonnelImportService` | `deps.get_personnel_service` |
| `domain.shared_costs` | `SharedCostImportService` | `deps.get_shared_cost_service` |
| `domain.notifications` | `NotificationService` | `deps.get_notification_service` |
| `domain.consolidation.dashboard` | `DashboardService` | `deps.get_dashboard_service` |
| `domain.consolidation.report` | `ConsolidatedReportService` | `deps.get_report_service` |
| `domain.consolidation.export` | `ConsolidatedExportService` | `deps.get_export_service` |
| `domain.accounts` | `AccountService` | `deps.get_account_service` |
| `domain._shared.queries` | `org_unit_code_to_id_map` | `deps.get_org_unit_map` |
| All `api/v1/*.py` sub-routers | `*_router` | `router.py` |

---

## 5. Side Effects

- `router.py`: No side effects. Pure assembly.
- `deps.py`: DB session is created and closed per request. `current_user` touches the `sessions` table on every authenticated request (updates `last_active_at`).
- Schema validation errors (Pydantic) are caught by the global exception handler and return 422 `Unprocessable Entity`.

---

## 6. Gotchas

- **`router.py` is 100% imports and `include_router` calls.** Zero logic. If it approaches 30 lines, it is already doing too much.
- **`deps.py` must not contain business logic.** It provides dependency factories only. The factory pattern (`get_cycle_service` returns a `CycleService` instance constructed with injected session) is the correct pattern.
- **`current_user` is defined in `deps.py`, NOT in `core/security/auth_service.py`.** `deps.current_user` wraps `AuthService.current_user` for FastAPI `Depends` compatibility.
- **`csrf_dep` is applied selectively.** Only POST, PATCH, DELETE routes include `Depends(csrf_dep)`. GET routes do NOT. The convention is to add `csrf_dep` as a parameter to each state-mutating route definition, not globally in the router.
- **Schema files ≤500 lines each.** If `schemas/consolidation.py` exceeds 400 lines, split into `schemas/dashboard.py` + `schemas/report.py`.
- **`Decimal` serialization (CR-036).** Every schema with monetary amounts uses `Decimal` type. The `model_config = ConfigDict(json_encoders={Decimal: str})` must be present on every such class.
- **Error envelope.** Route handlers do NOT catch domain exceptions. They propagate to `app/main.py`'s global exception handler. The envelope shape `{"error": {"code", "message", "details"}, "request_id"}` is produced there. Schemas in `schemas/errors.py` (if present) document this; they are NOT produced by individual routes.
- **`get_org_unit_map` caching:** Per-request caching is achieved by the FastAPI `Depends` mechanism (same `Depends(get_org_unit_map)` in a route evaluates once per request). No module-level cache.

---

## 7. Verbatim Outputs

- All error responses: `{"error": {"code": "...", "message": "...", "details": [...]}, "request_id": "..."}` — produced by global handler in `main.py`.
- `422 Unprocessable Entity`: Pydantic validation failure on request body/query params.
- `401 Unauthorized`: `AUTH_001` from `current_user`.
- `403 Forbidden`: `RBAC_001` / `RBAC_002` from `RBAC.require_role` / `require_scope`.

---

## 8. Consistency Constraints

**CR-001 — Error code registry single source**
*"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
`deps.py` raises `AUTH_001`, `AUTH_002`. Route handlers propagate errors from domain services without adding new codes.

**CR-032 — RBAC scope matrix completeness**
*"This route declares `Depends(RBAC.require_role(...))` AND, where the URL contains a resource id, `Depends(RBAC.require_scope(resource_type, resource_id_param))`. Both must be present — `require_role` alone is insufficient for scoped resources."*
Each sub-router's route handlers must satisfy this. `router.py` itself does not declare RBAC — that is in the individual route files.

**CR-033 — Server-side scope filter applied even on list endpoints**
*"List endpoints call `await RBAC.scoped_org_units(user, db)` and pass the resulting set as a WHERE filter on `org_unit_id`."*
Enforced in individual service methods (M4, M5, M6, M7). `deps.py` provides `current_user` + `get_session` for this purpose.

---

## 9. Tests

### `test_router.py` (API)

1. **`test_all_routes_registered`** — enumerate `app.routes`; assert all expected prefixes `/api/v1/cycles`, `/api/v1/templates`, etc. are present.
2. **`test_unauthenticated_protected_route_returns_401`** — GET `/api/v1/cycles` without session cookie; assert 401.
3. **`test_unknown_route_returns_404`** — GET `/api/v1/nonexistent`; assert 404.

### `test_deps.py` (API)

1. **`test_current_user_valid_session_returns_user`** — valid `bc_session` cookie; assert `User` returned with correct `id`.
2. **`test_current_user_expired_session_raises_auth_001`** — expired JWT; assert `UnauthenticatedError(AUTH_001)`.
3. **`test_csrf_dep_passes_with_matching_header`** — POST with matching `X-CSRF-Token` and `bc_csrf`; assert no error.
4. **`test_csrf_dep_fails_with_mismatched_header`** — POST with wrong `X-CSRF-Token`; assert `UnauthenticatedError(AUTH_002)`.

### `test_schemas.py` (unit — consolidation schemas)

1. **`test_consolidated_report_row_delta_pct_is_string`** — construct `ConsolidatedReportRowSchema` with `delta_pct='9.1'`; serialize to JSON; assert `delta_pct` is a string in JSON output (not a number).
2. **`test_decimal_amount_serialized_as_string`** — `actual=Decimal('1234.56')`; serialize; assert JSON contains `"1234.56"` (string) not `1234.56` (number) (CR-036).
3. **`test_dashboard_response_sentinel_field`** — construct with `sentinel='尚未開放週期'`; assert field serializes correctly.
