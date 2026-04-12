# BCMS — Budget Collection Management System

Enterprise annual budget collection platform. SystemAdmin opens a budget cycle, the platform auto-generates per-department Excel templates, department managers upload completed budgets, HR and Finance upload personnel and shared-cost data, and FinanceAdmin monitors consolidated reports with per-account actuals vs. budget comparisons.

## Tech Stack

| Layer    | Technology                                      |
|----------|--------------------------------------------------|
| Backend  | Python 3.12+, FastAPI, SQLAlchemy 2, Alembic     |
| Frontend | React 18, TypeScript, Vite, Mantine 7, Zustand   |
| Database | PostgreSQL 16                                     |
| Auth     | SSO (OIDC/SAML) with role-based access control    |

## Prerequisites

- [Python 3.12+](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Node.js 18+](https://nodejs.org/)
- [pnpm](https://pnpm.io/)
- [Docker](https://www.docker.com/products/docker-desktop/) (for PostgreSQL)

## Quick Start

### 1. Start PostgreSQL

```bash
docker run --name bcms-pg -d \
    -e POSTGRES_USER=bcms -e POSTGRES_PASSWORD=bcms \
    -e POSTGRES_DB=bcms_test -p 5432:5432 postgres:16
```

### 2. Backend

```bash
cd backend
uv sync --all-extras
export BC_DATABASE_URL="postgresql+asyncpg://bcms:bcms@localhost:5432/bcms_test"
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

API available at http://localhost:8000 (docs at http://localhost:8000/docs).

### 3. Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

App available at http://localhost:5173.

## Testing

```bash
# Backend
cd backend
uv run pytest

# Frontend
cd frontend
pnpm test
```

## Project Structure

```
BCMS/
  backend/         # FastAPI application
    src/           # Source code
    tests/         # Unit and integration tests
    alembic/       # Database migrations
  frontend/        # React application
    src/           # Source code
    tests/         # Unit tests
  docs/            # Documentation
  specs/           # Specifications
```

## License

Proprietary. Internal use only.
