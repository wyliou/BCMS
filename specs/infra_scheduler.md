# Spec: infra/scheduler

Module: `backend/src/app/infra/scheduler/__init__.py` | Tests: `backend/tests/unit/infra/test_scheduler.py` | FRs: FR-005, FR-020

## Exports

```python
def register_cron(expr: str, func: Callable[[], None], name: str) -> None:
    """Register a cron-triggered callback with APScheduler.

    Must be called before get_scheduler().start(). Subsequent calls with the same
    name replace the existing job (idempotent registration).

    Args:
        expr (str): Cron expression (5-field: minute hour day_of_month month day_of_week).
            e.g. '0 9 * * *' for daily 09:00.
        func (Callable[[], None]): Callable with no arguments. Should be a thin wrapper
            that calls the real domain service. Must NOT raise — wrap in try/except.
        name (str): Unique job name for APScheduler job ID.

    Raises:
        ValueError: If expr is not a valid cron expression.
    """

def get_scheduler() -> AsyncIOScheduler:
    """Return the module-level APScheduler AsyncIOScheduler instance.

    Creates the instance on first call with timezone from settings.BC_TIMEZONE.

    Returns:
        AsyncIOScheduler: The shared scheduler instance.
    """

def shutdown_scheduler() -> None:
    """Shut down the scheduler gracefully.

    Called during FastAPI lifespan shutdown. Waits for running jobs to complete
    (wait=True). Idempotent.
    """
```

## Imports

| Module | Symbols |
|---|---|
| `apscheduler.schedulers.asyncio` | `AsyncIOScheduler` |
| `apscheduler.triggers.cron` | `CronTrigger` |
| `zoneinfo` | `ZoneInfo` |
| `app.config` | `get_settings` |
| `structlog` | `get_logger` |

## Side Effects

- `get_scheduler()` creates a module-level singleton `_scheduler: AsyncIOScheduler | None` on first call.
- `register_cron` adds a `CronTrigger` job to the scheduler.
- `get_scheduler().start()` is called from `app/main.py` lifespan startup.
- `shutdown_scheduler()` stops the scheduler thread.

## Gotchas

- **TZ configuration (CR-038):** `CronTrigger` must be created with `timezone=ZoneInfo(settings.timezone)`. APScheduler's default TZ is UTC — if this is omitted, the 09:00 cron fires at 09:00 UTC = 17:00 Taipei, which is wrong.
- **Cron callback exception isolation (CR-035):** Each registered `func` must wrap its body in `try/except Exception` at the outermost level. If it raises, log at ERROR and return — never re-raise to the scheduler thread.
- APScheduler 3.10.x uses `AsyncIOScheduler` for async FastAPI apps; jobs are fired via `asyncio.ensure_future`. If the callback is a coroutine, APScheduler 3.x requires `coalesce=True` to prevent overlap on slow callbacks.
- `register_cron` should use `scheduler.add_job(..., id=name, replace_existing=True)` for idempotency.

## Consistency Constraints

- **CR-038 Stage B check:** *"`infra.scheduler` configures APScheduler with `timezone=ZoneInfo(settings.timezone)`. The cron expression `0 9 * * *` is interpreted as 09:00 in Asia/Taipei, NOT UTC."*
- **CR-035 Stage B check:** *"The cron callback wraps its body in `try/except Exception` at the outermost layer. On exception: `log.error('scheduler.callback_failed', ...)` and return — never re-raise."*

## Tests

1. `test_register_cron_adds_job` — register a no-op cron; `get_scheduler().get_jobs()` contains it.
2. `test_register_cron_idempotent` — register same name twice; only one job in scheduler.
3. `test_scheduler_timezone_is_asia_taipei` — with `BC_TIMEZONE=Asia/Taipei`, next run for `0 9 * * *` after `2026-04-12T00:00:00+08:00` is `2026-04-12T09:00:00+08:00`.
4. `test_shutdown_idempotent` — call `shutdown_scheduler()` twice; no exception.
5. `test_callback_exception_does_not_crash_scheduler` — register a callback that raises; assert scheduler is still running and subsequent job fires.
