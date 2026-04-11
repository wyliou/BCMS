# BCMS Backend

Enterprise Annual Budget Collection Platform — Python/FastAPI backend. The system enables annual budget collection across all organisational units (departments 4000–0500): SystemAdmin opens a budget cycle, the platform auto-generates per-department Excel templates, department managers upload completed budgets, HR and Finance upload personnel and shared-cost data, and FinanceAdmin monitors consolidated reports with per-account actuals vs. budget comparisons. All access is controlled via SSO (OIDC/SAML) with role-based permissions enforced server-side.

## Quick start

```bash
# Install all dependencies (including dev extras)
uv sync --all-extras

# Run the test suite
uv run pytest

# Start the development server
uv run uvicorn app.main:app --reload
```

## Database migrations

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Generate a new migration from model changes
uv run alembic revision --autogenerate -m "describe change"
```

## Integration tests (Postgres required)

Integration tests under `tests/integration/` require a live PostgreSQL 16
reachable at `BC_DATABASE_URL`. Without it, the tests skip cleanly (marked
via `@pytest.mark.integration` + a reachability probe in
`tests/integration/conftest.py`).

Quick local setup with Docker:

```bash
docker run --name bcms-pg -d \
    -e POSTGRES_USER=bcms -e POSTGRES_PASSWORD=bcms \
    -e POSTGRES_DB=bcms_test -p 5432:5432 postgres:16

export BC_DATABASE_URL="postgresql+asyncpg://bcms:bcms@localhost:5432/bcms_test"
uv run alembic upgrade head
uv run pytest tests/integration -q
```

All other `BC_*` variables have sensible defaults for local development;
tests seed the minimum set via `tests/conftest.py`.

