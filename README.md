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

> On subsequent runs, use `docker start bcms-pg` instead of `docker run`.

### 2. Create the backend `.env` file

Copy the example below to `backend/.env`:

```dotenv
# --- Required -----------------------------------------------------------
BC_DATABASE_URL=postgresql+asyncpg://bcms:bcms@localhost:5432/bcms_test
BC_CRYPTO_KEY=<hex-encoded 32-byte key>
BC_AUDIT_HMAC_KEY=<hex-encoded 32-byte key>

# --- Dev SSO (no real IdP) ----------------------------------------------
BC_SSO_ROLE_MAPPING={"BCMS_ADMIN":"SystemAdmin"}

# --- Frontend proxy (must match the port Vite is running on) -------------
BC_API_BASE_URL=http://localhost:5173
BC_FRONTEND_ORIGIN=http://localhost:5173
```

Generate the required crypto keys:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Run twice — once for BC_CRYPTO_KEY, once for BC_AUDIT_HMAC_KEY
```

### 3. Backend

```bash
cd backend
uv sync --all-extras
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs

### 4. Frontend (separate terminal)

```bash
cd frontend
pnpm install
pnpm dev
```

- App: http://localhost:5173

> **Important:** Open the app via the **frontend** URL (`:5173`), not the backend (`:8000`).
> The Vite dev server proxies `/api/v1/*` requests to the backend automatically.

### 5. Log in

When no SSO provider is configured, the app uses a built-in dev identity
(`FakeSSO`) that logs you in as **SystemAdmin** automatically. Just click
the login button on the frontend.

## Environment Variables

All variables use the `BC_` prefix. The backend reads them from the process
environment or from `backend/.env` (pydantic-settings, case-insensitive).

### Required

| Variable | Description |
|---|---|
| `BC_DATABASE_URL` | Async SQLAlchemy URL, e.g. `postgresql+asyncpg://user:pass@host:5432/db` |
| `BC_CRYPTO_KEY` | Hex-encoded 32-byte AES-256 master key (64 hex chars) |
| `BC_AUDIT_HMAC_KEY` | Hex-encoded HMAC key for audit chain (at least 32 bytes) |

### Optional (with defaults)

| Variable | Default | Description |
|---|---|---|
| `BC_API_BASE_URL` | `http://localhost:8000` | Base URL for SSO redirects. Set to the frontend URL in dev. |
| `BC_FRONTEND_ORIGIN` | `http://localhost:5173` | CORS origin and post-login redirect target. |
| `BC_SSO_ROLE_MAPPING` | `{}` | JSON object mapping IdP groups to app roles, e.g. `{"AD_GROUP":"SystemAdmin"}` |
| `BC_SSO_PROVIDER` | `oidc` | SSO protocol (`oidc` or `saml`). |
| `BC_SSO_CLIENT_ID` | `""` | OIDC client ID. |
| `BC_SSO_CLIENT_SECRET` | `None` | OIDC client secret. |
| `BC_SSO_ISSUER` | `""` | OIDC issuer URL. Leave empty for dev mode (FakeSSO). |
| `BC_SSO_DISCOVERY_URL` | `None` | OIDC discovery URL (alternative to issuer). |
| `BC_SSO_REDIRECT_URI` | `""` | OIDC callback URI registered with the IdP. |
| `BC_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `BC_SESSION_IDLE_MINUTES` | `30` | Session idle timeout. |
| `BC_SESSION_ABSOLUTE_HOURS` | `8` | Session absolute timeout. |
| `BC_COOKIE_SECURE` | `true` | Set `false` if testing over plain HTTP. |
| `BC_SMTP_HOST` | `""` | SMTP server for email notifications. |
| `BC_SMTP_PORT` | `587` | SMTP port. |
| `BC_MAX_UPLOAD_BYTES` | `10485760` | Max file upload size (10 MB). |
| `BC_TIMEZONE` | `Asia/Taipei` | Application timezone for schedules/deadlines. |

## Roles

| Role | Scope | Description |
|---|---|---|
| `SystemAdmin` | Global | Full CRUD — user admin, org structure, cycles |
| `FinanceAdmin` | Global | Dashboard, reports, shared-cost imports, cycle management |
| `HRAdmin` | Global | Personnel data imports |
| `FilingUnitManager` | Org unit | Upload budgets for assigned unit |
| `UplineReviewer` | Org unit | Review budgets for child units |
| `CompanyReviewer` | Global | Company-wide budget review |
| `ITSecurityAuditor` | Global | Audit log access |

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
    .env           # Local environment variables (not committed)
  frontend/        # React application
    src/           # Source code
    tests/         # Unit tests
  docs/            # Documentation
  specs/           # Specifications
```

## Troubleshooting

| Problem | Solution |
|---|---|
| `ValidationError: crypto_key / audit_hmac_key Field required` | Create `backend/.env` with the required keys (see step 2). |
| Login redirects to `:8000` and shows JSON error | Set `BC_API_BASE_URL` to the frontend URL (e.g. `http://localhost:5173`). |
| `Port 5173 is in use, trying another one...` | Vite picked a different port (e.g. 5174). Update `BC_API_BASE_URL` and `BC_FRONTEND_ORIGIN` in `.env` to match, then restart the backend. |
| `docker: Error ... name bcms-pg is already in use` | Container exists — run `docker start bcms-pg` instead. |
| Docker daemon not running | Start Docker Desktop and wait for it to fully initialize. |

## License

Proprietary. Internal use only.
