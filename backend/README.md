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
