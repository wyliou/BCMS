# Spec: infra/jobs

Modules:
- `backend/src/app/infra/jobs/__init__.py` (public API: `enqueue`, `register_handler`, `get_status`, `register_all_handlers`)
- `backend/src/app/infra/jobs/worker.py` (worker process entrypoint)

Tests: `backend/tests/integration/infra/test_jobs.py`

## FRs

- FR-017 (async report export → job enqueue → worker → email on completion)

## Exports

```python
async def enqueue(
    job_type: str,
    payload: dict[str, object],
    *,
    db: AsyncSession,
    user_id: UUID | None = None,
) -> UUID:
    """Enqueue a durable job by inserting a row into job_runs with status='queued'.

    Args:
        job_type (str): Registered handler key (e.g. 'export_consolidated_report').
        payload (dict[str, object]): Job-specific data serialized to JSONB.
        db (AsyncSession): Active async session (caller commits).
        user_id (UUID | None): ID of the user who initiated the job, for tracking.

    Returns:
        UUID: The new job_run.id.

    Raises:
        InfraError: code='SYS_001' on DB failure.
        ValueError: If job_type is not registered via register_handler.
    """

def register_handler(job_type: str, handler: Callable[[dict], Awaitable[dict]]) -> None:
    """Register an async handler function for a job type.

    Must be called before the worker starts. The handler receives the job payload
    and must return a result dict (stored in job_runs.result).

    Args:
        job_type (str): Unique job type string matching what callers pass to enqueue.
        handler (Callable[[dict], Awaitable[dict]]): Async function taking the payload dict
            and returning a result dict.
    """

async def get_status(job_id: UUID, db: AsyncSession) -> dict[str, object]:
    """Return the current status and metadata for a job.

    Args:
        job_id (UUID): The job_run.id.
        db (AsyncSession): Active async session.

    Returns:
        dict[str, object]: Keys: id, status, job_type, enqueued_at, started_at,
            finished_at, error_message, result (subset; result_file_path excluded
            — callers use /exports/{id}/file endpoint for file access).

    Raises:
        NotFoundError: code='UPLOAD_008' ... actually uses a generic 404 path;
            for jobs specifically raise InfraError or NotFoundError as appropriate.
            Document: raises AppError if job not found.
    """

def register_all_handlers() -> None:
    """Register all known job handlers at app startup.

    Called from app/main.py lifespan. Imports and registers:
    - 'export_consolidated_report' → domain.consolidation.export.ReportExportHandler.run
    (Additional handlers added here as new job types are created.)
    """
```

### `worker.py`

```python
async def run_worker() -> None:
    """Main worker loop: poll job_runs for 'queued' rows, execute handlers, update status.

    Loop:
    1. SELECT ... FOR UPDATE SKIP LOCKED to claim one queued job.
    2. Mark status='running', set worker_id, started_at.
    3. Call registered handler(job.payload).
    4. On success: mark status='succeeded', set result, finished_at.
    5. On handler exception: increment attempts; if attempts < max_attempts, re-enqueue;
       else mark status='failed', set error_message, finished_at.
    6. Sleep BC_JOBS_POLL_INTERVAL_SECONDS between polls.

    Raises:
        SystemExit: On SIGTERM/SIGINT (graceful shutdown).
    """

def main() -> None:
    """Entrypoint for `python -m app.infra.jobs.worker`.

    Configures logging, loads settings, starts async event loop running run_worker().
    """
```

## Imports

| Module | Symbols |
|---|---|
| `sqlalchemy` | `select`, `update` |
| `sqlalchemy.ext.asyncio` | `AsyncSession` |
| `uuid` | `UUID`, `uuid4` |
| `datetime` | `datetime` |
| `asyncio` | `sleep`, `run` |
| `signal` | `signal`, `SIGTERM` |
| `app.core.errors` | `InfraError`, `AppError` |
| `app.infra.db.session` | `get_session`, `configure_engine`, `dispose_engine` |
| `app.core.clock` | `now_utc` |
| `app.config` | `get_settings` |
| `structlog` | `get_logger` |

## Side Effects

- `enqueue` inserts a row to `job_runs`.
- Worker loop: reads and updates `job_runs` rows.
- Worker process runs as a separate OS process supervised independently from the API.

## DB Schema for `job_runs` (architecture §6)

```
job_runs (
  id UUID PK, job_type VARCHAR(64), status job_status, payload JSONB,
  result JSONB, result_file_path_enc BYTEA, error_message TEXT,
  enqueued_by UUID FK users, enqueued_at TIMESTAMPTZ, started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ, attempts INT, worker_id VARCHAR(128)
)
```

## Concurrency Safety

Worker uses `SELECT ... FOR UPDATE SKIP LOCKED` to atomically claim one queued job per poll. This prevents two worker processes from double-claiming the same job. If the application is single-worker (as per the architecture), this is belt-and-suspenders.

## Gotchas

- `register_all_handlers()` is called at startup BEFORE any request is served. The consolidation export handler is the only handler at Batch 1; additional handlers are added in later batches without changing the worker loop.
- Worker process has its own DB engine (created in `main()`), separate from the API process engine.
- Handler return value (a dict) is stored in `job_runs.result` as JSONB. If the handler produces a file, it stores the `result_file_path_enc` in the `job_runs` row (encrypted storage key).
- `BC_JOBS_MAX_ATTEMPTS` controls retry count. On the final failure, send the failure notification email (via `notifications.send`) — but this is handled inside `ReportExportHandler`, not in the generic worker loop.
- Graceful shutdown: worker catches `SIGTERM`, finishes the current job, exits cleanly.
- `enqueue` validates that `job_type` is in the registered handler map; raises `ValueError` on unknown types.

## Consistency Constraints

- **CR-001 Stage B check:** *"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
  - Raises `InfraError("SYS_001", ...)` on DB failure.

## Tests

### Integration tests (require Postgres)

1. `test_enqueue_creates_job_run_row` — `enqueue("export_consolidated_report", {...})` → verify row in `job_runs` with `status='queued'`.
2. `test_get_status_returns_queued` — after enqueue; `get_status(job_id)` → `status == "queued"`.
3. `test_worker_executes_handler_and_marks_succeeded` — register a test handler that returns `{"ok": True}`; run worker for one iteration; assert `status == "succeeded"`, `result == {"ok": True}`.
4. `test_worker_marks_failed_after_max_attempts` — register a handler that always raises; run worker for `max_attempts` iterations; assert `status == "failed"`.
5. `test_enqueue_unknown_job_type_raises` — `enqueue("nonexistent_type", {})` raises `ValueError`.
6. `test_skip_locked_prevents_double_claim` — two worker coroutines polling simultaneously; each job claimed by exactly one worker.
