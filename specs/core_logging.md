# Spec: core/logging

Module: `backend/src/app/core/logging.py` | Tests: `backend/tests/unit/core/test_logging.py` | FRs: (none — shared utility)

## Exports

```python
def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for JSON output to stdout.

    Args:
        log_level (str): Logging level string — DEBUG/INFO/WARN/ERROR. Defaults to "INFO".
    """
```

## Imports

- `structlog`: `configure`, `make_filtering_bound_logger`, `stdlib`, `processors`
- `logging`: `basicConfig`, `getLevelName`

## Side Effects

- Calls `structlog.configure(...)` once at app startup.
- Calls `logging.basicConfig(...)` to configure stdlib bridge.
- Idempotent if called multiple times with the same level.

## Gotchas

- `configure_logging` is called from `app/main.py` lifespan startup, passing `settings.log_level`.
- JSON processor chain: `add_log_level` → `add_logger_name` → `TimeStamper(fmt="iso", utc=True)` → `StackInfoRenderer` → `JSONRenderer`.
- `event` field naming: structlog emits the positional string as `event` — all call-sites must use snake_case noun.verb convention.
- Required fields (`timestamp`, `level`, `event`, `request_id`, `user_id`, `module`) are added by middleware (request_id) and by call-site kwargs (`user_id=user.id`, `module=__name__`); this module does not inject them automatically.
- NEVER log raw passwords, JWTs, file contents, or PII.

## Tests

1. `test_configure_logging_runs_without_error` — call `configure_logging("INFO")`; assert no exception.
2. `test_log_level_debug_accepted` — call `configure_logging("DEBUG")`; assert no exception.
3. `test_structlog_produces_json` — after configuring, use a structlog logger to emit one record; capture via `io.StringIO`; parse JSON; assert `"event"` key present.
4. `test_timestamp_is_utc_iso` — captured log record has `"timestamp"` that parses as UTC ISO-8601.
5. `test_invalid_level_raises` — `configure_logging("VERBOSE")` raises `ValueError` or equivalent.

## Constraints

None.
