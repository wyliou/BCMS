# Spec: core/errors

Module: `backend/src/app/core/errors.py` | Tests: `backend/tests/unit/core/test_errors.py`

## FRs

- FR-001 → CYCLE_001 (409)
- FR-002 → CYCLE_002 (409)
- FR-003 → CYCLE_003 (409)
- FR-006 → CYCLE_004 (409), CYCLE_005 (409)
- FR-007 → ACCOUNT_001 (404)
- FR-008 → ACCOUNT_002 (400)
- FR-009 → TPL_001 (500)
- FR-010 → TPL_002 (404)
- FR-011 → UPLOAD_001 (413), UPLOAD_002 (400), UPLOAD_003–006 (400 row-level), UPLOAD_007 (400), UPLOAD_008 (404)
- FR-021 → AUTH_001 (503), AUTH_002 (400), AUTH_003 (403), AUTH_004 (401)
- FR-022 → RBAC_001 (403), RBAC_002 (403)
- FR-023 → AUDIT_001 (500), AUDIT_002 (400)
- FR-024 → PERS_001–003 (400 row-level), PERS_004 (400)
- FR-027 → SHARED_001–003 (400 row-level), SHARED_004 (400)
- FR-015/017 → REPORT_001 (404), REPORT_002 (410)
- FR-013/018/020 → NOTIFY_001 (502), NOTIFY_002 (500), NOTIFY_003 (404)
- Infra → SYS_001 (500), SYS_002 (500), SYS_003 (500)

## Exports

```python
class AppError(Exception):
    """Base application exception carrying an error code and HTTP status.

    Args:
        code (str): Error code key from ERROR_REGISTRY (e.g. 'UPLOAD_007').
        message (str): Human-readable message (may include dynamic context).
        http_status (int): HTTP status code (sourced from ERROR_REGISTRY).
        details (list[dict] | None): Row-level or field-level error details.
    """
    code: str
    message: str
    http_status: int
    details: list[dict] | None

class BatchValidationError(AppError):
    """Raised after collect-then-report validation finds one or more row errors.

    Args:
        code (str): Batch-level code, e.g. 'UPLOAD_007', 'PERS_004', 'SHARED_004', 'ACCOUNT_002'.
        errors (list[RowError]): All row-level errors collected during validation.
    """

class NotFoundError(AppError):
    """Resource not found (HTTP 404 by registry default).

    Args:
        code (str): e.g. 'ACCOUNT_001', 'TPL_002', 'NOTIFY_003'.
        message (str): Context-specific message.
    """

class ConflictError(AppError):
    """Conflicting state or duplicate resource (HTTP 409 by registry default).

    Args:
        code (str): e.g. 'CYCLE_001', 'CYCLE_004'.
        message (str): Context-specific message.
    """

class ForbiddenError(AppError):
    """RBAC or role-mapping denial (HTTP 403 by registry default).

    Args:
        code (str): e.g. 'RBAC_001', 'RBAC_002', 'AUTH_003'.
        message (str): Context-specific message.
    """

class UnauthenticatedError(AppError):
    """Session expired or invalid (HTTP 401 by registry default).

    Args:
        code (str): e.g. 'AUTH_004'.
        message (str): Context-specific message.
    """

class InfraError(AppError):
    """Infrastructure / adapter failure (HTTP 500 or 503 by registry).

    Args:
        code (str): e.g. 'SYS_001', 'AUTH_001', 'NOTIFY_001'.
        message (str): Describes the failing subsystem.
    """

ERROR_REGISTRY: dict[str, tuple[int, str]]
```

`ERROR_REGISTRY` is the single source of truth. Every key below MUST appear in exactly this dict with `(http_status, default_message_template)`:

| Code | HTTP | Default message template |
|---|---|---|
| `AUTH_001` | 503 | `"Identity provider unreachable"` |
| `AUTH_002` | 400 | `"SSO callback signature or state mismatch"` |
| `AUTH_003` | 403 | `"No role mapping found for this SSO account"` |
| `AUTH_004` | 401 | `"Session or refresh token expired"` |
| `RBAC_001` | 403 | `"Insufficient role for this action"` |
| `RBAC_002` | 403 | `"Resource is outside your permitted scope"` |
| `CYCLE_001` | 409 | `"A non-closed cycle already exists for this fiscal year"` |
| `CYCLE_002` | 409 | `"One or more filing units are missing a manager"` |
| `CYCLE_003` | 409 | `"Cycle can only be opened from Draft state"` |
| `CYCLE_004` | 409 | `"Write operations are not permitted on a Closed cycle"` |
| `CYCLE_005` | 409 | `"Reopen window has expired"` |
| `ACCOUNT_001` | 404 | `"Account code not found"` |
| `ACCOUNT_002` | 400 | `"Actuals import failed: one or more rows are invalid"` |
| `TPL_001` | 500 | `"Template generation failed"` |
| `TPL_002` | 404 | `"Template has not been generated for this org unit"` |
| `UPLOAD_001` | 413 | `"File size exceeds 10 MB limit"` |
| `UPLOAD_002` | 400 | `"Row count exceeds 5000 row limit"` |
| `UPLOAD_003` | 400 | `"Department code does not match the assigned org unit"` |
| `UPLOAD_004` | 400 | `"Required cell is empty"` |
| `UPLOAD_005` | 400 | `"Amount format is invalid"` |
| `UPLOAD_006` | 400 | `"Amount must be zero or positive"` |
| `UPLOAD_007` | 400 | `"Budget upload validation failed"` |
| `UPLOAD_008` | 404 | `"Upload record not found"` |
| `PERS_001` | 400 | `"Department ID not found in org tree"` |
| `PERS_002` | 400 | `"Account code is not in the personnel category"` |
| `PERS_003` | 400 | `"Personnel budget amount must be positive"` |
| `PERS_004` | 400 | `"Personnel import validation failed"` |
| `SHARED_001` | 400 | `"Department ID not found in org tree"` |
| `SHARED_002` | 400 | `"Account code is not in the shared_cost category"` |
| `SHARED_003` | 400 | `"Shared cost amount must be positive"` |
| `SHARED_004` | 400 | `"Shared cost import validation failed"` |
| `REPORT_001` | 404 | `"No data found for cycle and scope"` |
| `REPORT_002` | 410 | `"Export job failed"` |
| `NOTIFY_001` | 502 | `"SMTP relay unreachable"` |
| `NOTIFY_002` | 500 | `"Failed to persist resubmit request record"` |
| `NOTIFY_003` | 404 | `"Notification record not found"` |
| `AUDIT_001` | 500 | `"Audit hash chain verification failed"` |
| `AUDIT_002` | 400 | `"Audit filter parameters are invalid"` |
| `SYS_001` | 500 | `"Database connection failed"` |
| `SYS_002` | 500 | `"Storage system unavailable"` |
| `SYS_003` | 500 | `"Unhandled internal error"` |

## Imports

- `__future__`: `annotations`
- `dataclasses`: `field` (if needed for `details`)
- No third-party imports.

## Side Effects

None. Pure exception class definitions.

## Gotchas

- `BatchValidationError.__init__` must accept `errors: list[RowError]` and convert them via `[e.to_dict() for e in errors]` to populate `details`. Import `RowError` from `domain._shared.row_validation` would create a circular import — instead, `BatchValidationError` accepts `errors: list[dict]` or `errors: list` at construction and callers pass `[e.to_dict() for e in result.errors]`. The subclass does NOT import `RowError`.
- All subclasses read `http_status` from `ERROR_REGISTRY[code]` automatically; callers must NOT pass `http_status` explicitly for the subclasses (it's looked up in `__init_subclass__` or each subclass `__init__`).
- The global exception handler in `app/main.py` imports `AppError` and `ERROR_REGISTRY` from this module.

## Verbatim Outputs (error envelope shape from architecture §3)

```json
{
  "error": {
    "code": "UPLOAD_007",
    "message": "Budget upload validation failed",
    "details": [
      {"row": 12, "column": "dept_code", "code": "UPLOAD_003", "reason": "..."}
    ]
  },
  "request_id": "abcd1234"
}
```

## Consistency Constraints

- **CR-001 Stage B check:** *"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
  - This module **IS** the owner of `ERROR_REGISTRY`; all 38 codes listed above must be present at initial commit.

## Tests

### `AppError`
1. `test_app_error_stores_code_message_status` — construct `AppError("SYS_003", "oops", http_status=500)`, assert attributes match.
2. `test_app_error_details_default_none` — `details` is `None` when not passed.
3. `test_app_error_is_exception` — `isinstance(err, Exception)` is True.

### Subclasses
4. `test_batch_validation_error_http_400` — `BatchValidationError("UPLOAD_007", errors=[])` → `http_status == 400`.
5. `test_batch_validation_error_details_populated` — pass two dicts; `err.details` contains them.
6. `test_not_found_error_http_404` — `NotFoundError("ACCOUNT_001", "not found")` → `http_status == 404`.
7. `test_conflict_error_http_409` — `ConflictError("CYCLE_001", "dup")` → `http_status == 409`.
8. `test_forbidden_error_http_403` — `ForbiddenError("RBAC_001", "denied")` → `http_status == 403`.
9. `test_unauthenticated_http_401` — `UnauthenticatedError("AUTH_004", "expired")` → `http_status == 401`.
10. `test_infra_error_http_500` — `InfraError("SYS_001", "db down")` → `http_status == 500`.
11. `test_auth_001_is_503` — `InfraError("AUTH_001", "idp")` → `http_status == 503`.

### `ERROR_REGISTRY`
12. `test_registry_has_all_38_codes` — `len(ERROR_REGISTRY) == 38` (counts match the table above).
13. `test_registry_values_are_int_str_tuples` — every value is `(int, str)`.
14. `test_all_codes_match_prefix_pattern` — every key matches `[A-Z]+_[0-9]{3}`.
