# Spec: infra/db

Modules:
- `backend/src/app/infra/db/session.py`
- `backend/src/app/infra/db/base.py`
- `backend/src/app/infra/db/helpers.py`

Tests:
- `backend/tests/integration/infra/test_db_session.py`
- `backend/tests/integration/infra/test_db_helpers.py`

## FRs

- FR-012, FR-025, FR-028 (versioning via `next_version`)
- All modules depend on `get_session` and `Base`.

## Exports

### `session.py`

```python
def configure_engine(database_url: str, pool_size: int = 10, max_overflow: int = 5) -> None:
    """Create and store the module-level async SQLAlchemy engine.

    Args:
        database_url (str): asyncpg SQLAlchemy URL.
        pool_size (int): Connection pool size. Defaults to 10.
        max_overflow (int): Pool overflow. Defaults to 5.
    """

async def dispose_engine() -> None:
    """Dispose (close) the async engine and connection pool.

    Called during FastAPI lifespan shutdown.
    """

async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an AsyncSession per request.

    Yields:
        AsyncSession: SQLAlchemy async session. Rolled back on exception,
            committed on clean exit only when caller commits explicitly.

    Raises:
        InfraError: code='SYS_001' if the engine is not configured or
            asyncpg raises a connection error.
    """
```

### `base.py`

```python
class Base(DeclarativeBase):
    """SQLAlchemy ORM DeclarativeBase for all BCMS models.

    All ORM model classes must inherit from this Base.
    """
```

### `helpers.py`

```python
async def next_version(db: AsyncSession, model: type, **filters: object) -> int:
    """Return MAX(version) + 1 for the given model and filter set, or 1 if no rows exist.

    Must be called inside the same transaction that inserts the new row to prevent
    race conditions. The table's UNIQUE constraint on (cycle_id, ..., version) is the
    final safety net for concurrent callers.

    Args:
        db (AsyncSession): Active async session, already in a transaction.
        model (type): SQLAlchemy ORM model class with a `version` column.
        **filters (object): Column=value filter pairs passed to WHERE clause
            (e.g. cycle_id=some_uuid, org_unit_id=other_uuid).

    Returns:
        int: Next version number (≥ 1).

    Raises:
        InfraError: code='SYS_001' on DB failure.
    """
```

## Imports

| Module | Symbols |
|---|---|
| `sqlalchemy.ext.asyncio` | `create_async_engine`, `AsyncSession`, `async_sessionmaker` |
| `sqlalchemy.orm` | `DeclarativeBase` |
| `sqlalchemy` | `select`, `func` |
| `collections.abc` | `AsyncIterator` |
| `asyncpg` | exception types (caught, wrapped into `InfraError`) |
| `app.core.errors` | `InfraError` |

## Side Effects

- `configure_engine` creates a module-level `_engine` and `_session_factory`.
- `dispose_engine` calls `await _engine.dispose()`.
- `get_session` opens and closes a session per FastAPI request lifecycle.

## Gotchas

- **`next_version` race safety:** the function issues `SELECT MAX(version) ... FOR UPDATE` on the owning row (or relies on `SKIP LOCKED`-style optimistic retry). The simpler approach: use `SELECT MAX(version)` + rely on the `UNIQUE (cycle_id, org_unit_id, version)` constraint to raise `IntegrityError` on collision, which the caller can catch and retry (one retry is sufficient for serialized uploads from the same unit). Document this behavior explicitly.
- **Session factory pattern:** Use `async_sessionmaker(bind=engine, expire_on_commit=False)` so that ORM objects remain accessible after `await db.commit()` without triggering lazy loads.
- **`get_session` is a FastAPI `Depends` generator**, not a context manager. Do NOT call `db.commit()` inside `get_session`; the route handler owns commit timing.
- `Base` must be imported by every ORM model file so that SQLAlchemy's metadata registry is populated before Alembic runs.
- `dispose_engine` should be idempotent (guard against double-dispose).

## Consistency Constraints

- **CR-001 Stage B check:** *"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
  - `get_session` wraps asyncpg errors as `InfraError("SYS_001", ...)`.

## Tests

### `test_db_session.py` (integration — requires Postgres)

1. `test_get_session_yields_async_session` — use `get_session()` as async context manager; assert type is `AsyncSession`.
2. `test_session_rollback_on_exception` — insert a row, raise inside the block, assert the row does not exist after rollback.
3. `test_dispose_engine_cleans_pool` — call `dispose_engine()`; assert subsequent `get_session()` raises or reinitializes.

### `test_db_helpers.py` (integration — requires Postgres)

4. `test_next_version_returns_1_when_no_rows` — empty table; `next_version(db, BudgetUpload, cycle_id=cid, org_unit_id=oid)` → `1`.
5. `test_next_version_increments` — insert version=1; call again → returns `2`.
6. `test_next_version_filters_correctly` — two different `org_unit_id` values each with v1; calling for one unit returns `2` (relative to its own max), not `3`.
7. `test_next_version_concurrent_integrity` — (stress test) two concurrent tasks insert for the same `(cycle_id, org_unit_id)`; one gets `v1`, one gets `v2`; no `IntegrityError` leaks to caller (retry logic handles it).
