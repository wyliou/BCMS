# Spec: main

Module: `backend/src/app/main.py` | Tests: `backend/tests/api/test_main.py`

## FRs

- FR-021 (auth error envelope shape)
- FR-022 (RBAC error → audit record)
- FR-023 (request_id in every response)

## Exports

```python
app: FastAPI
```

The `app` object is the sole public export. All other symbols are module-level private setup.

## Module Responsibilities

1. Construct `FastAPI` instance with title, version, `lifespan`.
2. Add `request_id` middleware: generates UUID v4 per request, attaches to `request.state.request_id`, returns in `X-Request-ID` response header.
3. Add CORS middleware allowing `settings.frontend_origin`.
4. Add optional IP allowlist middleware: if `BC_IP_ALLOWLIST` is set, reject requests from IPs outside the CIDR list with 403.
5. Register global exception handler for `AppError` → JSON error envelope.
6. Register global fallback handler for `Exception` → `SYS_003` envelope.
7. Mount the `api/v1` router at `/api/v1`.
8. `lifespan` context manager: startup runs `configure_logging`, `configure_db_engine`, `register_job_handlers`, `register_cron_jobs`; shutdown calls `dispose_db_engine`, `scheduler.shutdown()`.

## Imports

| Module | Symbols |
|---|---|
| `fastapi` | `FastAPI`, `Request`, `Response` |
| `fastapi.middleware.cors` | `CORSMiddleware` |
| `fastapi.responses` | `JSONResponse` |
| `uuid` | `uuid4` |
| `contextlib` | `asynccontextmanager` |
| `structlog` | `get_logger` |
| `app.config` | `get_settings` |
| `app.core.logging` | `configure_logging` |
| `app.core.errors` | `AppError` |
| `app.infra.db.session` | `configure_engine`, `dispose_engine` |
| `app.infra.scheduler` | `get_scheduler`, `shutdown_scheduler` |
| `app.infra.jobs` | `register_all_handlers` |
| `app.api.v1.router` | `router` |

## Side Effects

### Startup (lifespan)
1. `configure_logging(settings.log_level)` — configure structlog.
2. `configure_engine(settings.database_url, ...)` — create async SQLAlchemy engine.
3. `register_all_handlers()` — register durable job handler functions (e.g. `ReportExportHandler`).
4. `get_scheduler().start()` — start APScheduler; registers cron callbacks from domain modules.
5. Log `app.startup` at INFO.

### Shutdown (lifespan)
1. `shutdown_scheduler()` — stop APScheduler gracefully.
2. `dispose_engine()` — close connection pool.
3. Log `app.shutdown` at INFO.

## Error Envelope (verbatim from architecture §3)

Global exception handler converts `AppError` to:

```json
{
  "error": {
    "code": "<err.code>",
    "message": "<err.message>",
    "details": "<err.details or null>"
  },
  "request_id": "<request.state.request_id>"
}
```

Unhandled `Exception` produces the same shape with `code="SYS_003"`.

## Gotchas

- `request_id` middleware must run BEFORE the global exception handler so that the `request_id` is available when errors are formatted.
- Use `Starlette` `BaseHTTPMiddleware` or a low-level ASGI middleware for `request_id` injection; avoid FastAPI middleware that swallows exceptions.
- The `lifespan` parameter replaces deprecated `on_startup`/`on_shutdown` events (FastAPI 0.115+).
- The exception handler must call `await audit_service.record(...)` only for `ForbiddenError` (RBAC_001/RBAC_002) and `UnauthenticatedError` (AUTH_004) per FR-022 — but during Batch 0 the `audit` module does not yet exist. The global handler must be structured so the audit call is a pluggable hook: e.g. an `_audit_error_hook: Callable | None = None` set during app startup by the audit module. At Batch 0, the hook is `None` and the handler skips audit. At Batch 1 (when audit is built), the hook is registered.
- IP allowlist: if `BC_IP_ALLOWLIST` is non-empty, parse comma-separated CIDRs using `ipaddress.ip_network`; compare against `request.client.host` using `ipaddress.ip_address(host) in network`.

## Consistency Constraints

- **CR-001 Stage B check:** *"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
  - The global handler emits `SYS_003` for unhandled exceptions; this code must be present in `ERROR_REGISTRY`.

## Tests

### Request ID Middleware
1. `test_response_has_x_request_id_header` — any GET to a test route; assert response header `X-Request-ID` is a valid UUID.
2. `test_request_id_is_unique_per_request` — two requests; assert different IDs.

### Global Exception Handler
3. `test_app_error_returns_correct_status_and_envelope` — inject a route that raises `ConflictError("CYCLE_001", "dup")`; assert 409, body matches envelope shape.
4. `test_batch_validation_error_returns_400_with_details` — route raises `BatchValidationError("UPLOAD_007", errors=[{"row": 1, "code": "UPLOAD_003", "reason": "x"}])`; assert 400, `details` in body.
5. `test_unhandled_exception_returns_sys_003` — route raises `RuntimeError("boom")`; assert 500, `code == "SYS_003"`.

### Lifespan
6. `test_startup_does_not_raise` — `AsyncClient(app=app)` context manager exits cleanly; assert no exception.
7. `test_cors_header_present` — OPTIONS request from `settings.frontend_origin`; assert `Access-Control-Allow-Origin` matches.
