---
status: complete
current_step: 5
prd_source: docs/PRD v4.3.md
prd_checksum: 39114f4a
product_category: Web App (React)
completed_at: 2026-04-10
---

# Architecture: Enterprise Annual Budget Collection Platform / 全集團部門年度預算蒐集平台

> Generated: 2026-04-10
> PRD: docs/PRD v4.3.md

<!--
=============================================================================
AI IMPLEMENTATION GUIDE

This document + PRD = complete implementation context.
- PRD defines WHAT (requirements with Input/Rules/Output/Error)
- Architecture defines HOW (stack, structure, patterns, specifications)

IMPLEMENTATION ORDER:
1. Install tech stack dependencies (use Build Commands)
2. Create directory structure (use src_dir/test_dir markers)
3. Implement modules following boundaries (use Path, Exports, Depends On)
4. Build contracts matching module assignments
5. Apply coding patterns consistently
6. Follow implementation batch sequence (Section 9)

RULES:
- Follow naming conventions exactly
- Use error codes from taxonomy
- Keep modules isolated per boundaries
- Follow logging pattern for all log output
- Respect side-effect ownership
- Follow error propagation convention
=============================================================================
-->

---

## 1. Technology Stack

### Backend (Python)

| Category | Choice | Version | Rationale |
|----------|--------|---------|-----------|
| Language | Python | 3.12 | Modern type hints, async support, mature data/Excel ecosystem |
| Web Framework | FastAPI | 0.115.x | Async-first, built-in OpenAPI, native Pydantic v2 integration |
| ASGI Server | Uvicorn (+ Gunicorn workers) | 0.32.x / 23.x | Production-grade ASGI; Gunicorn supervises Uvicorn workers |
| Data Validation | Pydantic | 2.9.x | Request/response schemas, settings management |
| ORM | SQLAlchemy (async) | 2.0.x | Mature; works with async PostgreSQL via asyncpg |
| Migrations | Alembic | 1.13.x | Standard SQLAlchemy migration tool |
| DB Driver | asyncpg | 0.30.x | Fastest async PostgreSQL driver |
| Auth — OIDC client | Authlib | 1.3.x | Supports OIDC + SAML 2.0 (FR-021 §14) |
| Auth — JWT | PyJWT | 2.9.x | Verify JWT issued by IdP / mint short-lived API tokens |
| Excel parsing/generation | openpyxl | 3.1.x | Reads/writes XLSX; preserves cell formatting for templates (FR-009/011) |
| CSV parsing | stdlib `csv` + Pandas (optional) | — | HR/Shared cost imports (FR-024/027) |
| Email sending | aiosmtplib | 3.0.x | Async SMTP to internal relay; intranet only |
| Cron scheduler | APScheduler | 3.10.x | **Cron-only**: deadline reminders (FR-005, FR-020). Lightweight, no broker. |
| Durable job runner | DB-backed `job_runs` table + single worker process | — | **Long-running / restart-safe** jobs: async report exports (FR-017, >1000 units). APScheduler is unsuitable here because exports may run minutes and must survive process restart. Worker polls `job_runs` for `queued` rows, marks `running`, persists status/result, sends Email on completion. |
| Cryptography | cryptography | 43.x | AES-256-GCM column encryption (§14), audit hash chain (FR-023) |
| Logging | structlog | 24.x | Structured JSON logs for audit + ops |
| Testing | pytest + pytest-asyncio + httpx | 8.x / 0.24 / 0.27 | Standard FastAPI test stack |
| Lint/Format | ruff | 0.7.x | Combined linter + formatter (replaces black + flake8 + isort) |
| Type Check | pyright | 1.1.x | Strict mode for `src/` |
| Package Manager | uv | 0.5.x | Fast resolver, lockfile, virtualenv mgmt |

### Frontend (React)

| Category | Choice | Version | Rationale |
|----------|--------|---------|-----------|
| Language | TypeScript | 5.6.x | Type safety, IDE tooling |
| Framework | React | 18.3.x | PRD §1.3 / §14 (locked) |
| Build Tool | Vite | 5.4.x | Fast HMR, modern bundling |
| Routing | React Router | 6.28.x | SPA routing for role-differentiated screens |
| Server State | TanStack Query | 5.x | Caching, background refresh (Dashboard ≤5s, FR-004/014) |
| UI State | Zustand | 5.x | Lightweight client state |
| Forms | react-hook-form + zod | 7.x / 3.23 | Upload forms, schema validation |
| HTTP Client | axios | 1.7.x | Interceptors for JWT refresh + 401 handling |
| Component Library | Mantine | 7.x | **Locked.** Accessible (WCAG AA), traditional-Chinese-friendly, design-token compatible with PRD §8.1. Consolidated report (FR-015 three-column-group) built with TanStack Table + `@mantine/core` styling rather than a heavyweight DataGrid. |
| i18n | react-i18next | 15.x | zh-TW primary; English keys for technical labels (NFR-USE-001) |
| Charts/Tables | Mantine DataTable / TanStack Table | — | Consolidated reports (FR-015) |
| Excel/PDF download | Browser (server-generated) | — | Backend generates files, frontend triggers download |
| Testing | Vitest + React Testing Library | 2.x / 16.x | Unit + component tests |
| E2E Testing | Playwright | 1.48.x | Cross-browser (Chrome/Edge/Firefox per NFR-COMPAT-001) |
| Lint/Format | ESLint + Prettier | 9.x / 3.x | Standard JS/TS toolchain |
| Package Manager | pnpm | 9.x | Fast, disk-efficient |

### Database & Infra

| Category | Choice | Version | Rationale |
|----------|--------|---------|-----------|
| Database | PostgreSQL | 16.x | **Locked.** JSONB for audit metadata, mature backup/PITR (NFR-REL-002), `pg_stat_statements` for ops, ROW-LEVEL SECURITY available if needed. **NOTE:** AES-256 column encryption is **NOT** done via `pgcrypto` — keys would leak into `pg_stat_statements` and query logs. Encryption is performed in `infra/crypto` (Python `cryptography` AES-GCM) **before** INSERT and after SELECT. `pgcrypto` is only enabled for hashing helpers and `gen_random_uuid()`, not symmetric encryption. |
| Object Storage | Local encrypted volume (LUKS or equivalent) | — | **Locked.** Uploaded Excel/CSV files + generated templates + async exports; intranet-only single-host deployment. Backup via rsync/volume snapshot — see §7 Backup Contract. No S3/object-storage dependency. |
| Reverse Proxy | Nginx | stable | TLS termination, static asset serving, internal IP allowlist |
| Container Runtime | Docker | 27.x | Reproducible deploys to internal Linux hosts |
| Orchestration | docker-compose | 2.x | Sufficient for single-tenant intranet scale (target ~100–500 units) |
| Secrets | Environment file (.env) on host + filesystem ACL | — | Internal-only; no cloud KMS available |

### Build Commands

| Command | Value |
|---------|-------|
| Install (backend) | `uv sync` (in `backend/`) |
| Install (frontend) | `pnpm install` (in `frontend/`) |
| Test (backend) | `uv run pytest tests/ --tb=short` |
| Test (frontend) | `pnpm test` |
| Test (e2e) | `pnpm exec playwright test` |
| Lint (backend) | `uv run ruff check src/ --fix` |
| Lint (frontend) | `pnpm lint` |
| Type Check (backend) | `uv run pyright src/` |
| Type Check (frontend) | `pnpm exec tsc --noEmit` |
| Format (backend) | `uv run ruff format src/` |
| Format (frontend) | `pnpm exec prettier --write src/` |
| Build (backend) | `uv build` |
| Build (frontend) | `pnpm build` |
| DB migrate | `uv run alembic upgrade head` |
| DB new revision | `uv run alembic revision --autogenerate -m "msg"` |
| Run dev (backend) | `uv run uvicorn app.main:app --reload` |
| Run dev (frontend) | `pnpm dev` |

### Dependency Pinning Strategy

- **Locked deps (PRD §14 Decided):** React, FastAPI, PostgreSQL, Authlib, PyJWT, cryptography → **exact pin** (`==x.y.z` / `x.y.z`) in `pyproject.toml` / `package.json`. Lockfiles (`uv.lock`, `pnpm-lock.yaml`) committed.
- **Runtime deps:** Compatible range `>=x.y,<x+1` (semver-compatible) — pinned exactly in lockfile.
- **Dev/build tools (ruff, pyright, eslint, prettier):** Minimum version `>=` in manifest; lockfile pins exact.
- **Lockfiles MUST be committed.** CI installs from lockfile (`uv sync --frozen`, `pnpm install --frozen-lockfile`).

---

## 2. Project Structure

Monorepo: `backend/` (Python/FastAPI) + `frontend/` (React/Vite). Each has its own lockfile and CI lane.

<!-- src_dir: backend/src/ -->
<!-- src_dir_frontend: frontend/src/ -->
<!-- test_dir: backend/tests/ -->
<!-- test_dir_frontend: frontend/tests/ -->

```
budget-collection/
├── backend/
│   ├── pyproject.toml              # uv-managed deps + tool config
│   ├── uv.lock
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/               # DB migrations
│   ├── src/
│   │   └── app/
│   │       ├── __init__.py
│   │       ├── main.py             # FastAPI app entry point
│   │       ├── config.py           # Pydantic Settings (env vars)
│   │       ├── deps.py             # FastAPI dependency injection
│   │       ├── api/                # Route handlers (thin)
│   │       │   ├── v1/
│   │       │   │   ├── auth.py             # FR-021
│   │       │   │   ├── cycles.py           # FR-001~006
│   │       │   │   ├── accounts.py         # FR-007, 008
│   │       │   │   ├── templates.py        # FR-009, 010
│   │       │   │   ├── budget_uploads.py   # FR-011~013
│   │       │   │   ├── personnel.py        # FR-024~026
│   │       │   │   ├── shared_costs.py     # FR-027~029
│   │       │   │   ├── dashboard.py        # FR-014
│   │       │   │   ├── reports.py          # FR-015, 016, 017
│   │       │   │   ├── notifications.py    # FR-018, 019, 020
│   │       │   │   ├── audit.py            # FR-023
│   │       │   │   └── admin.py            # OrgUnit + Users
│   │       │   └── router.py
│   │       ├── domain/             # Pure business logic per capability
│   │       │   ├── _shared/                # Cross-domain helpers (no FRs)
│   │       │   │   ├── row_validation.py   # RowError, ValidationResult, clean_cell, parse_amount
│   │       │   │   └── queries.py          # org_unit_code_to_id_map, etc.
│   │       │   ├── cycles/
│   │       │   ├── accounts/
│   │       │   ├── templates/
│   │       │   ├── budget_uploads/
│   │       │   ├── personnel/
│   │       │   ├── shared_costs/
│   │       │   ├── consolidation/  # FR-015 cross-source aggregation
│   │       │   ├── notifications/
│   │       │   └── audit/
│   │       ├── infra/              # Side-effect owners
│   │       │   ├── db/
│   │       │   │   ├── session.py
│   │       │   │   ├── helpers.py          # next_version() and other shared SQL helpers
│   │       │   │   └── models/             # SQLAlchemy ORM models
│   │       │   ├── storage/        # Async file I/O for uploads (run_in_threadpool)
│   │       │   ├── excel/          # openpyxl read/write helpers
│   │       │   ├── csv_io/         # CSV decode + DictReader
│   │       │   ├── tabular.py      # parse_table(filename, bytes) — CSV/XLSX dispatcher
│   │       │   ├── email/          # aiosmtplib client
│   │       │   ├── crypto/         # AES-256, hash chain
│   │       │   ├── sso/            # Authlib OIDC/SAML client
│   │       │   ├── scheduler/      # APScheduler — cron triggers only (FR-005, FR-020)
│   │       │   └── jobs/           # Durable job runner (DB-backed) for FR-017 async exports
│   │       ├── schemas/            # Pydantic request/response models
│   │       └── core/
│   │           ├── errors.py       # AppError hierarchy + error code registry
│   │           ├── logging.py      # structlog config
│   │           ├── clock.py        # now_utc() — testability injection
│   │           └── security/       # M10: SSO callback, JWT, RBAC, sessions
│   │               ├── __init__.py
│   │               ├── auth_service.py
│   │               ├── rbac.py
│   │               ├── jwt.py
│   │               └── sessions.py
│   └── tests/
│       ├── unit/                   # Pure logic, no DB
│       ├── integration/            # Real Postgres (testcontainers or docker-compose)
│       ├── api/                    # FastAPI TestClient (httpx)
│       └── fixtures/               # Sample Excel/CSV files, JSON payloads
│
├── frontend/
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── playwright.config.ts
│   ├── public/
│   ├── src/
│   │   ├── main.tsx                # Vite entry
│   │   ├── App.tsx
│   │   ├── routes/                 # React Router config
│   │   ├── pages/
│   │   │   ├── auth/               # SSO callback
│   │   │   ├── upload/             # 填報單位主管 (FR-010, 011)
│   │   │   ├── dashboard/          # FR-014
│   │   │   ├── reports/            # FR-015, 016, 017
│   │   │   ├── personnel-import/   # HR Admin (FR-024)
│   │   │   ├── shared-cost-import/ # Finance Admin (FR-027)
│   │   │   ├── admin/              # Cycles, accounts, org tree
│   │   │   └── audit/              # IT auditor (FR-023)
│   │   ├── features/               # Feature-scoped components + hooks
│   │   │   ├── cycles/
│   │   │   ├── budget-uploads/
│   │   │   ├── personnel-import/
│   │   │   ├── shared-cost-import/
│   │   │   ├── consolidated-report/
│   │   │   ├── notifications/
│   │   │   └── audit/
│   │   ├── components/             # Shared, presentational
│   │   ├── api/                    # Generated/typed API client (axios + zod)
│   │   ├── hooks/
│   │   ├── stores/                 # Zustand stores
│   │   ├── i18n/                   # zh-TW translations
│   │   ├── styles/                 # Design tokens (PRD §8.1)
│   │   └── lib/
│   ├── tests/
│   │   ├── unit/                   # Vitest
│   │   └── e2e/                    # Playwright specs
│   └── index.html
│
├── deploy/
│   ├── docker-compose.yml          # postgres + backend + frontend(nginx)
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx.conf
│
├── docs/
│   ├── PRD v4.3.md
│   ├── architecture.md             # this file
│   └── validation-report.md
│
├── .env.example
├── .gitignore
└── README.md
```

---

## 3. Coding Patterns

### Naming Conventions

**Backend (Python):**

| Element | Convention | Example |
|---------|------------|---------|
| Source files | snake_case | `budget_upload_service.py` |
| Test files | `test_` prefix | `test_budget_upload_service.py` |
| Functions | snake_case | `validate_upload_rows()` |
| Classes / Pydantic models | PascalCase | `BudgetUploadCreate`, `CycleService` |
| SQLAlchemy ORM models | PascalCase singular | `BudgetUpload`, `OrgUnit` |
| DB tables | snake_case plural | `budget_uploads`, `org_units` |
| DB columns | snake_case | `fiscal_year`, `uploaded_at` |
| Constants | UPPER_SNAKE | `MAX_UPLOAD_BYTES`, `MAX_ROWS_PER_FILE` |
| Env vars | UPPER_SNAKE with `BC_` prefix | `BC_DATABASE_URL`, `BC_SMTP_HOST` |
| Error codes | `<AREA>_<NNN>` | `UPLOAD_001`, `AUTH_003` |
| API routes | kebab-case, plural resources | `/api/v1/budget-uploads` |

**Frontend (TypeScript/React):**

| Element | Convention | Example |
|---------|------------|---------|
| Component files | PascalCase | `ConsolidatedReport.tsx` |
| Hook files | camelCase, `use` prefix | `useBudgetUploads.ts` |
| Utility files | kebab-case | `format-currency.ts` |
| Functions | camelCase | `getUploadStatus()` |
| Components | PascalCase | `<ConsolidatedReport />` |
| Constants | UPPER_SNAKE | `STATUS_COLORS` |
| Types/Interfaces | PascalCase | `BudgetUploadDto` |
| Routes | kebab-case | `/personnel-import` |
| i18n keys | dot.notation snake_case | `upload.error.row_invalid` |

### Response Format

**API (FastAPI JSON):** Direct return of typed Pydantic models on success, FastAPI exception handlers map domain errors to a uniform error envelope.

```jsonc
// Success — handler returns Pydantic model
{
  "id": "uuid", "cycle_id": "uuid", "version": 3, ...
}

// Error — global exception handler emits this shape
{
  "error": {
    "code": "UPLOAD_002",
    "message": "Department code does not match assigned org unit",
    "details": [
      { "row": 12, "column": "account_code", "reason": "not in master" }
    ]
  },
  "request_id": "abcd1234"
}
```

HTTP status mapping is defined under Error Code Taxonomy below. All responses include an `X-Request-ID` header for cross-correlation with audit logs.

### Error Code Taxonomy

PRD has no formal error catalog; codes are derived from FR capability areas (PRD §2.4). Each code namespaces to a module so callers can dispatch on prefix.

| Prefix | Capability Area | Owning Module | HTTP Status |
|--------|-----------------|---------------|-------------|
| `AUTH_` | SSO + JWT verification (FR-021) | `infra/sso`, `core/security` | 401 |
| `RBAC_` | Role/scope checks (FR-022) | `core/security` | 403 |
| `CYCLE_` | Cycle lifecycle (FR-001~006) | `domain/cycles` | 400 / 409 |
| `ACCOUNT_` | Account master / actuals (FR-007, 008) | `domain/accounts` | 400 / 404 |
| `TPL_` | Template generation/download (FR-009, 010) | `domain/templates` | 400 / 500 |
| `UPLOAD_` | Budget Excel upload validation (FR-011~013) | `domain/budget_uploads` | 400 / 413 |
| `PERS_` | HR personnel import (FR-024~026) | `domain/personnel` | 400 |
| `SHARED_` | Shared-cost import (FR-027~029) | `domain/shared_costs` | 400 |
| `REPORT_` | Consolidation / export (FR-014~017) | `domain/consolidation` | 400 / 500 |
| `NOTIFY_` | Notifications / resubmit (FR-018~020) | `domain/notifications` | 400 / 502 |
| `AUDIT_` | Audit log query / write (FR-023) | `domain/audit` | 400 / 500 |
| `SYS_` | Unhandled / infra failures | any | 500 |

Codes use 3-digit sequence per prefix (`UPLOAD_001`..`UPLOAD_NNN`). Each code is defined exactly once in `core/errors.py` with its message template and HTTP status; FRs reference codes via comment markers.

**Code registry (referenced by §5 contracts):**

| Code | HTTP | Where raised | FR |
|---|---|---|---|
| `AUTH_001` | 503 | `infra/sso` IdP timeout / unreachable | FR-021 |
| `AUTH_002` | 400 | `infra/sso` callback signature/state mismatch | FR-021 |
| `AUTH_003` | 403 | `core/security` no role mapping for SSO subject | FR-021 |
| `AUTH_004` | 401 | `core/security` session/refresh expired | FR-021, NFR-SEC-002 |
| `RBAC_001` | 403 | `core/security` role missing | FR-022 |
| `RBAC_002` | 403 | `core/security` resource outside scope | FR-022 |
| `CYCLE_001` | 409 | `domain/cycles` fiscal year already has active cycle | FR-001 |
| `CYCLE_002` | 409 | `domain/cycles` filing unit missing manager | FR-002 |
| `CYCLE_003` | 409 | `domain/cycles` open attempted on non-Draft cycle | FR-003 |
| `CYCLE_004` | 409 | `domain/cycles` write attempted on Closed cycle | FR-006 |
| `CYCLE_005` | 409 | `domain/cycles` reopen window expired | FR-006 |
| `ACCOUNT_001` | 404 | `domain/accounts` account code not found | FR-007 |
| `ACCOUNT_002` | 400 | `domain/accounts` actuals import row invalid (collect-then-report) | FR-008 |
| `TPL_001` | 500 | `domain/templates` generation failed (reported per-unit, not raised globally unless infra) | FR-009 |
| `TPL_002` | 404 | `domain/templates` template not generated for unit | FR-010 |
| `UPLOAD_001` | 413 | `domain/budget_uploads` file size > 10 MB | FR-011 |
| `UPLOAD_002` | 400 | `domain/budget_uploads` row count > 5000 | FR-011 |
| `UPLOAD_003` | 400 (row-level) | `domain/budget_uploads` dept code mismatch | FR-011 |
| `UPLOAD_004` | 400 (row-level) | `domain/budget_uploads` required cell empty | FR-011 |
| `UPLOAD_005` | 400 (row-level) | `domain/budget_uploads` amount format invalid | FR-011 |
| `UPLOAD_006` | 400 (row-level) | `domain/budget_uploads` negative amount | FR-011 |
| `UPLOAD_007` | 400 | `domain/budget_uploads` batch validation failed (carries row errors) | FR-011 |
| `UPLOAD_008` | 404 | `budget_uploads`, `personnel`, `shared_costs` upload row not found by id | FR-011, FR-024, FR-027 |
| `PERS_001` | 400 (row-level) | `domain/personnel` dept_id not in org tree | FR-024 |
| `PERS_002` | 400 (row-level) | `domain/personnel` account code not personnel category | FR-024 |
| `PERS_003` | 400 (row-level) | `domain/personnel` amount must be positive | FR-024 |
| `PERS_004` | 400 | `domain/personnel` batch validation failed | FR-024 |
| `SHARED_001` | 400 (row-level) | `domain/shared_costs` dept_id not in org tree | FR-027 |
| `SHARED_002` | 400 (row-level) | `domain/shared_costs` account code not shared_cost category | FR-027 |
| `SHARED_003` | 400 (row-level) | `domain/shared_costs` amount must be positive | FR-027 |
| `SHARED_004` | 400 | `domain/shared_costs` batch validation failed | FR-027 |
| `REPORT_001` | 404 | `domain/consolidation` no data for cycle scope | FR-015 |
| `REPORT_002` | 410 | `domain/consolidation` export job failed | FR-017 |
| `NOTIFY_001` | 502 | `domain/notifications` SMTP unreachable | FR-013, FR-018, FR-020 |
| `NOTIFY_002` | 500 | `domain/notifications` resubmit log write failed (notification NOT sent) | FR-019 |
| `NOTIFY_003` | 404 | `domain/notifications` notification not found | FR-013 |
| `AUDIT_001` | 500 | `domain/audit` hash chain verification failed | FR-023 |
| `AUDIT_002` | 400 | `domain/audit` filter parameters invalid | FR-023 |
| `SYS_001` | 500 | infra DB unreachable | — |
| `SYS_002` | 500 | infra storage unavailable | — |
| `SYS_003` | 500 | unhandled exception | — |

### Logging Pattern

- **Library:** `structlog` configured to emit JSON to stdout (collected by container runtime).
- **Format:** Structured fields, never f-string templating.
  ```python
  log.info("budget_upload.accepted",
           cycle_id=cycle.id, org_unit_id=ou.id,
           upload_id=upload.id, version=upload.version,
           file_hash=upload.file_hash, user_id=current_user.id)
  ```
- **Required fields on every entry:** `timestamp` (ISO-8601 UTC), `level`, `event` (snake_case), `request_id`, `user_id` (when authenticated), `module`.
- **Levels:**
  - `ERROR` — handled domain failures returned to caller, infra failures
  - `WARN` — degraded states (notification bounce, retry exhausted, scheduler skipped run)
  - `INFO` — state transitions (cycle opened/closed, upload accepted, import completed, notification sent, login success/logout)
  - `DEBUG` — dev only; disabled in prod via `BC_LOG_LEVEL`
- **NEVER log:** raw passwords, full JWTs, raw uploaded file contents, PII (none expected — see PRD §9 PII Classification).
- **Audit vs application logs:** App logs are operational; **audit log entries (FR-023) are written to the `audit_logs` table by `domain/audit`**, not via structlog. Both may share the same event for correlation but they are distinct sinks.

### Error Propagation Convention

Two patterns coexist; the choice is dictated by FR semantics:

| Pattern | When to Use | Mechanism |
|---------|-------------|-----------|
| **Raise immediate** | Single fatal error: auth failure, RBAC denial, cycle in wrong state, resource not found, infra failure | Raise a subclass of `AppError(code, message, details=None, http_status=...)`. Global FastAPI exception handler converts to error envelope + writes audit log if applicable. |
| **Collect-then-report** | Multi-row validation: FR-008 actuals import, FR-011 budget upload, FR-024 personnel import, FR-027 shared cost import | Validators return a `ValidationResult(rows, errors)` where `errors: list[RowError]` and `valid` is a derived property. `RowError`, `ValidationResult`, `clean_cell`, and `parse_amount(allow_zero=...)` live in **`domain/_shared/row_validation.py`** so the four importers share one definition (no per-domain copies). If `not result.valid`, the service raises `BatchValidationError(code="UPLOAD_007"\|"PERS_004"\|"SHARED_004"\|"ACCOUNT_002", details=[e.to_dict() for e in result.errors])` — **integral commit semantics: zero rows persisted on any failure.** |

**Module conventions:**
- `domain/*` services raise `AppError` subclasses; never return error codes inline.
- `api/*` route handlers do not catch domain exceptions — they propagate to the global handler.
- `infra/*` modules wrap library exceptions into `AppError` (e.g., `asyncpg.ConnectionError` → `SYS_001`).
- `domain/budget_uploads`, `domain/personnel`, `domain/shared_costs` use the **collect-then-report** pattern internally before raising the final batch error.
- The global handler ensures every error response carries an `X-Request-ID` and that `domain/audit` records the failure for FR-022 (403) and FR-021 (401 mapping failures).

### Side-Effect Ownership

Each side effect has exactly **one** owning module. Domain modules invoke owners through dependency-injected interfaces; they never construct paths or talk to libraries directly.

| Side Effect | Owner Module | Non-owners Must |
|-------------|--------------|-----------------|
| File reads/writes (uploads, generated templates, exports) | `infra/storage` | Call `await storage.save()`, `await storage.read()`, `await storage.delete()` — never `open()` directly. The module wraps blocking disk I/O in `run_in_threadpool` so handlers and worker callbacks can `await` it without stalling the event loop. |
| Excel parsing/generation | `infra/excel` | Call `excel.open_workbook()`, `excel.read_rows()`, `excel.workbook_to_bytes()` |
| CSV parsing | `infra/csv_io` | Call `csv_io.parse_dicts(bytes)` for raw CSV |
| Tabular upload dispatch (CSV vs XLSX by filename) | `infra/tabular` | Call `tabular.parse_table(filename, bytes)` — single entry point used by every importer (`accounts/actuals`, `personnel`, `shared_costs`); never re-implement extension dispatch in domain code |
| DB reads/writes | `infra/db` (session) + `domain/*` repos | Domain code uses repository methods; route handlers never query directly |
| HTTP egress (SSO discovery, IdP) | `infra/sso` | Call `sso.exchange_code()`, `sso.fetch_userinfo()` |
| SMTP egress | `infra/email` | Call `email.send(template_name, recipient, context)` — never construct MIME inline |
| Symmetric encryption | `infra/crypto` | Call `crypto.encrypt_field()`, `crypto.decrypt_field()` |
| Audit hash chain | `infra/crypto` (hashing) + `domain/audit` (sequencing) | Other modules call `audit.record(action, resource, details)`; never write `audit_logs` rows directly |
| **Cron-triggered jobs** (deadline reminders FR-005/020) | `infra/scheduler` | Register cron triggers at startup via `scheduler.register_cron(...)`; trigger callbacks are thin wrappers that call domain services. **No long-running work here** — anything that may exceed a few seconds must be enqueued to `infra/jobs`. |
| **Durable async jobs** (FR-017 large-report export, future long-running work) | `infra/jobs` | Enqueue via `jobs.enqueue(job_type, payload)` returning a `job_id`; never spawn background tasks ad-hoc. Status queryable via `jobs.get_status(job_id)`. Worker process is supervised separately from the API process. |
| Logging | Each module via shared logger | Always use `structlog.get_logger(__name__)`; never `print()` |
| Path construction | `infra/storage` | All other modules receive opaque storage keys/handles |
| Time | `core/clock` (`now_utc()`) | Never call `datetime.now()` in domain code — required for testability and deterministic snapshots |

### Session & Token Transport (FR-021, NFR-SEC-002)

Browser ↔ API session is conducted over **HttpOnly secure cookies**, not `Authorization: Bearer` headers. Rationale: the app surfaces XSS-attractive content (uploaded Excel filenames, row-level error messages echoing user input). HttpOnly cookies cannot be read by injected JavaScript.

| Concern | Decision |
|---------|----------|
| Session token storage | `Set-Cookie: bc_session=<jwt>; HttpOnly; Secure; SameSite=Strict; Path=/` |
| Refresh token storage | `Set-Cookie: bc_refresh=<jwt>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth/refresh` |
| CSRF protection | Double-submit cookie pattern: server sets `bc_csrf=<random>; Secure; SameSite=Strict` (readable by JS); frontend mirrors value into `X-CSRF-Token` header on every state-changing request; backend verifies match |
| Idle timeout | 30 minutes (NFR-SEC-002). Backend tracks `last_activity_at` per session; any authenticated request rolls the timer. After 30 min idle, refresh fails → user re-authenticates via SSO. |
| Absolute session lifetime | 8 hours (cap; even active sessions force re-auth at end of working day) |
| Logout | Backend invalidates session record; clears all three cookies via `Max-Age=0` |
| 401 / 403 frontend handling | axios interceptor detects 401 → triggers silent refresh; on refresh failure → redirects to SSO entry; never retries 403 (RBAC denial is terminal) |

**Frontend never sees the JWT.** All auth state is "am I logged in?" booleans derived from a `/api/v1/auth/me` call. This means localStorage/sessionStorage hold zero credentials.

---

## 4. Module Boundaries

### Domain & Core Modules (own FRs)

| # | Module | Path | Test Path | Responsibility | Implements | Exports | Depends On |
|---|--------|------|-----------|----------------|------------|---------|------------|
| M1 | `cycles` | `backend/src/app/domain/cycles/` | `backend/tests/unit/cycles/` + `backend/tests/integration/cycles/` | Budget cycle lifecycle state machine (Draft/Open/Closed), filing-unit list resolution from org tree, reminder-schedule storage, deadline-reminder dispatcher (queries unsubmitted units via shared `infra/db` repo, calls `notifications`), cycle reopen workflow. **Does NOT call `templates` or `consolidation`** — those calls live in the api/v1 orchestrator and in dispatch logic respectively. | FR-001, FR-002, FR-003, FR-005, FR-006 | `CycleService.create()`, `.open()`, `.close()`, `.reopen()`, `.get(cycle_id)`, `.get_status(cycle_id)`, `.list_filing_units(cycle_id)`, `.assert_open(cycle_id)`, `.set_reminder_schedule()`, `.dispatch_deadline_reminders()`, `CycleStatus` enum | `notifications`, `audit`, `security`, `infra/db`, `infra/scheduler`, `core/clock` |
| M2 | `accounts` | `backend/src/app/domain/accounts/` | `backend/tests/unit/accounts/` | Account master (operational/personnel/shared_cost categories), bulk actuals import validation | FR-007, FR-008 | `AccountService.list()`, `.upsert()`, `.get_by_code()`, `.import_actuals(cycle_id, file)`, `AccountCategory` enum | `audit`, `security`, `domain/_shared`, `infra/db`, `infra/tabular`, `infra/storage` |
| M3 | `templates` | `backend/src/app/domain/templates/` | `backend/tests/unit/templates/` + `backend/tests/integration/templates/` | Per-filing-unit Excel template generation (operational accounts only, prefilled actuals), download authorization, regeneration on failure | FR-009, FR-010 | `TemplateService.generate_for_cycle(cycle_id)`, `.regenerate(cycle_id, org_unit_id)`, `.download(cycle_id, org_unit_id, user)` | `cycles`, `accounts`, `audit`, `security`, `infra/excel`, `infra/storage` |
| M4 | `budget_uploads` | `backend/src/app/domain/budget_uploads/` | `backend/tests/unit/budget_uploads/` + `backend/tests/integration/budget_uploads/` | Budget Excel upload validation (size, rows, dept code, required cells, amount format/sign), version snapshot, upload confirmation notification trigger | FR-011, FR-012, FR-013 | `BudgetUploadService.upload(cycle_id, org_unit_id, file, user)`, `.list_versions(cycle_id, org_unit_id)`, `.get(upload_id)`, `.get_latest(cycle_id, org_unit_id)`, `BudgetUploadValidator.validate(workbook)` returning shared `ValidationResult` | `cycles`, `accounts`, `notifications`, `audit`, `security`, `domain/_shared`, `infra/excel`, `infra/storage`, `infra/db` (uses `db.helpers.next_version`) |
| M5 | `personnel` | `backend/src/app/domain/personnel/` | `backend/tests/unit/personnel/` + `backend/tests/integration/personnel/` | HR personnel-budget CSV/Excel import (org-unit + personnel-category code + positive amount validation), version snapshot, finance notification | FR-024, FR-025, FR-026 | `PersonnelImportService.import_(cycle_id, file, user)`, `.list_versions(cycle_id)`, `.get(upload_id)`, `PersonnelImportValidator.validate(rows)` returning shared `ValidationResult` | `cycles`, `accounts`, `notifications`, `audit`, `security`, `domain/_shared`, `infra/tabular`, `infra/storage`, `infra/db` (uses `db.helpers.next_version`) |
| M6 | `shared_costs` | `backend/src/app/domain/shared_costs/` | `backend/tests/unit/shared_costs/` + `backend/tests/integration/shared_costs/` | Shared-cost CSV/Excel import (org-unit + shared-cost-category code + positive amount), version snapshot, affected-department notification | FR-027, FR-028, FR-029 | `SharedCostImportService.import_(cycle_id, file, user)`, `.list_versions(cycle_id)`, `.get(upload_id)`, `.diff_affected_units(prev_version, new_version)`, `SharedCostImportValidator.validate(rows)` returning shared `ValidationResult` | `cycles`, `accounts`, `notifications`, `audit`, `security`, `domain/_shared`, `infra/tabular`, `infra/storage`, `infra/db` (uses `db.helpers.next_version`) |
| M7 | `consolidation` | `backend/src/app/domain/consolidation/` | `backend/tests/unit/consolidation/` + `backend/tests/integration/consolidation/` | Dashboard status aggregation (per-role scoping), three-source consolidated report (operational + personnel + shared cost) at 1000處+ levels, budget-vs-actuals comparison, async export job orchestration | FR-014, FR-015, FR-016, FR-017 | `DashboardService.status_for_user(cycle_id, user)`, `ConsolidatedReportService.build(cycle_id, scope)`, `.export_async(cycle_id, scope, format, user)` returning `job_id`, `ReportExportHandler` (registered with `infra/jobs`) | `cycles`, `budget_uploads`, `personnel`, `shared_costs`, `accounts`, `security`, `audit`, `infra/db`, `infra/jobs`, `infra/excel`, `infra/storage` |
| M8 | `notifications` | `backend/src/app/domain/notifications/` | `backend/tests/unit/notifications/` + `backend/tests/integration/notifications/` | Email dispatch (template selection, delivery status tracking, bounce flagging), resubmit-request creation + history, deadline-reminder Email batches | FR-013, FR-018, FR-019, FR-020, FR-026, FR-029 (notify portion) | `NotificationService.send(template, recipient, context)`, `.send_batch(template, recipients, context)`, `.list_failed()`, `.resend(notification_id)`, `ResubmitRequestService.create(cycle_id, org_unit_id, requester, reason)`, `.list(cycle_id, org_unit_id)` | `audit`, `security`, `infra/email`, `infra/db`, `core/clock` |
| M9 | `audit` | `backend/src/app/domain/audit/` | `backend/tests/unit/audit/` + `backend/tests/integration/audit/` | Append-only audit log writes with hash-chain integrity, filtered query interface, chain verification | FR-023 | `AuditService.record(action, resource_type, resource_id, user, ip, details)`, `.query(filters)`, `.verify_chain(start, end)`, `AuditAction` enum | `infra/db`, `infra/crypto`, `core/clock` |
| M10 | `security` | `backend/src/app/core/security/` | `backend/tests/unit/security/` + `backend/tests/integration/security/` | SSO callback handling (OIDC/SAML via Authlib), JWT mint/verify, session lifecycle (cookie issue/refresh/logout), CSRF token mgmt, RBAC scope checks (role + org-unit visibility per FR-022) | FR-021, FR-022 | `AuthService.handle_sso_callback(provider, payload)`, `.refresh_session(refresh_token)`, `.logout(session_id)`, `.current_user(request)`, `RBAC.require_role(role)`, `RBAC.require_scope(user, resource)`, `RBAC.scoped_org_units(user)` | `audit`, `infra/sso`, `infra/db`, `infra/crypto`, `core/clock` |
| M11 | `api` | `backend/src/app/api/v1/` | `backend/tests/api/` | **Orchestrator only.** Thin FastAPI route handlers — parse request → call domain service → serialize response. NO business logic, NO regex, NO math, NO file I/O. Owns route declaration, request validation (Pydantic schemas), response shaping, dependency injection wiring. | (none — exposes all FRs via HTTP) | `router` (FastAPI APIRouter aggregating all v1 routes) | All M1–M10 |

### Infrastructure Adapters (called by domain modules — own no FRs)

These modules own side effects per §3 Side-Effect Ownership table. They are listed here for path-consistency validation only.

| Module | Path | Purpose |
|--------|------|---------|
| `infra/db` | `backend/src/app/infra/db/` | SQLAlchemy async session, ORM models, plus `helpers.py` (`next_version(db, model, **filters)` shared by every importer) |
| `infra/storage` | `backend/src/app/infra/storage/` | Async encrypted-volume file I/O for uploads/templates/exports — `save`/`read`/`delete` are `async` and offload blocking disk work via `run_in_threadpool` |
| `infra/excel` | `backend/src/app/infra/excel/` | openpyxl read/write helpers |
| `infra/csv_io` | `backend/src/app/infra/csv_io/` | CSV decode (`parse_dicts`) — UTF-8 only, rejects Big5 |
| `infra/tabular` | `backend/src/app/infra/tabular.py` | `parse_table(filename, bytes)` — single CSV/XLSX dispatcher used by every importer; thin wrapper over `csv_io` + `excel` |
| `infra/email` | `backend/src/app/infra/email/` | aiosmtplib client, MIME builder, template renderer |
| `infra/sso` | `backend/src/app/infra/sso/` | Authlib OIDC/SAML client, IdP discovery |
| `infra/crypto` | `backend/src/app/infra/crypto/` | AES-256-GCM column encryption, audit hash-chain primitives |
| `infra/scheduler` | `backend/src/app/infra/scheduler/` | APScheduler — cron triggers only (FR-005, FR-020) |
| `infra/jobs` | `backend/src/app/infra/jobs/` | DB-backed durable job runner (FR-017 async exports), worker process supervised separately |
| `core/clock` | `backend/src/app/core/clock.py` | `now_utc()` injection point for testability |
| `core/errors` | `backend/src/app/core/errors.py` | `AppError` hierarchy, error code registry |
| `core/logging` | `backend/src/app/core/logging.py` | structlog config |

### Cross-Domain Helpers (own no FRs)

`domain/_shared/` holds primitives that multiple domain modules need but that don't belong in any single domain. The leading underscore signals "private to the domain layer" — `api/v1` and `infra/*` MUST NOT import from here.

| Module | Path | Purpose |
|--------|------|---------|
| `domain/_shared/row_validation` | `backend/src/app/domain/_shared/row_validation.py` | `RowError`, `ValidationResult`, `clean_cell`, `parse_amount(allow_zero=...)`, `AmountParseError` — shared by every collect-then-report importer |
| `domain/_shared/queries` | `backend/src/app/domain/_shared/queries.py` | `org_unit_code_to_id_map(db)` and other small SELECTs that more than one importer needs |

### Inter-Module Interfaces

For each non-trivial dependency edge, the contract between caller and provider:

#### `api/v1.cycles_router.open_cycle()` — pipeline orchestration (not a domain dep)
- **Step 1:** `RBAC.require_role(FinanceAdmin)`
- **Step 2:** `CycleService.open(cycle_id)` → state Draft→Open, audit event, returns `(cycle, filing_units)`
- **Step 3:** `TemplateService.generate_for_cycle(cycle, filing_units)` → returns `list[TemplateGenerationResult]` (per-unit success/failure)
- **Step 4:** `NotificationService.send_batch("cycle_opened", recipients=managers_of(filing_units), context=cycle)` → returns batch_id
- **Step 5:** Returns combined `OpenCycleResponse` to caller
- **Error propagation:** Step 2 raises `CYCLE_002`/`CYCLE_003` (immediate). Step 3 collects per-unit failures into the response (no abort) — surfaced via dashboard for FR-009 retry. Step 4 bounces are flagged in `notifications` table (no abort). Steps 3 + 4 infra failures raise `TPL_001` / `NOTIFY_001` and the cycle stays Open (it's already committed at Step 2).
- **Why orchestrate here, not in `cycles`:** keeps `cycles` from forward-depending on `templates`, avoiding a back-edge through `templates → cycles` (template generation reads cycle metadata).

#### `cycles.dispatch_deadline_reminders()` → `notifications` (cron-triggered)
- **Provider:** `NotificationService.send_batch(template, recipients, context)`
- **Data flow:** Dispatcher queries `infra/db.repos.budget_uploads.unsubmitted_for_cycle(cycle_id)` directly (shared repo), filters by reminder schedule (FR-005 days_before), builds recipient list (filing-unit managers + their upline reviewers per FR-020), calls `send_batch`.
- **Why `infra/db` repo and not `consolidation`:** prevents `cycles → consolidation → budget_uploads` chain. The "unsubmitted" query is a single SQL join shared by both `cycles` (dispatcher) and `consolidation` (dashboard).
- **Error propagation:** Bounces flagged in `notifications` table (no caller); hard SMTP failure raises `NOTIFY_001` and the cron run logs at WARN.

#### `budget_uploads` → `accounts` + `cycles`
- **Provider (cycles):** `CycleService.assert_open(cycle_id)` — raises `CYCLE_004` if not Open
- **Provider (accounts):** `AccountService.get_operational_codes_set()` — returns set of valid operational account codes for the upload validator
- **Data flow:** Upload service validates cycle state first (raise immediate), then reads workbook via `infra/excel`, runs `BudgetUploadValidator` which uses the operational-codes set to check each row, returns `ValidationResult`. On `valid: false`, service raises `BatchValidationError(code=UPLOAD_007, details=result.errors)`.

#### `personnel` / `shared_costs` → `accounts`
- **Provider:** `AccountService.get_codes_by_category(category)` — returns set of personnel-category or shared_cost-category codes
- **Data flow:** Import validator filters incoming rows against the category-specific code set; rows referencing wrong-category codes fail with `PERS_002` / `SHARED_002`.
- **Error propagation:** collect-then-report; integral commit (zero rows persisted on any row failure).

#### `consolidation` → `budget_uploads` + `personnel` + `shared_costs`
- **Provider:** `.get_latest_by_cycle(cycle_id)` on each — returns the latest version's line items keyed by `(org_unit_id, account_code_id)`
- **Data flow:** Consolidation service reads three sources, joins by org-unit + account-code, filters by user scope (`RBAC.scoped_org_units`), returns `ConsolidatedReportRow` list. Three "last updated at" timestamps are also returned (per PRD §4.6 / FR-015).
- **Error propagation:** raise immediate on infra failure (`SYS_001`); empty data is not an error (returns empty rows).

#### `consolidation` → `infra/jobs`
- **Provider:** `jobs.enqueue("export_consolidated_report", payload)` returns `job_id`
- **Provider:** `jobs.register_handler("export_consolidated_report", ReportExportHandler.run)` at app startup
- **Data flow:** Report-export request returns `job_id` immediately (HTTP 202). Worker process polls `job_runs` table, picks up row, executes handler. Handler builds report, writes file via `infra/storage`, marks job `succeeded` with file path, calls `notifications.send` to email user.
- **Error propagation:** Handler exceptions caught by job runner, marked `failed` with error message; user receives failure Email.

#### `cycles` → `infra/scheduler` (startup wiring)
- **Provider:** `scheduler.register_cron(expr, callable, name)`
- **Data flow:** At app startup, `cycles` module registers `dispatch_deadline_reminders` as a daily 09:00 cron. Callback receives no args; queries all currently-open cycles, evaluates each against its reminder schedule, dispatches Email batches.
- **Error propagation:** Scheduler logs callback exceptions; never crashes the scheduler. Fatal callback errors logged at ERROR with `event=scheduler.callback_failed`.

#### `*` → `audit`
- **Provider:** `AuditService.record(action, resource_type, resource_id, user, ip, details)`
- **Data flow:** Every state-changing action calls `audit.record` AFTER successful DB commit but BEFORE returning to caller. Hash chain advances atomically with the new row insertion.
- **Error propagation:** raise immediate. If audit write fails, the calling operation is rolled back (audit failure means we cannot honor FR-023).

#### `*` → `security` (per-request)
- **Provider:** `RBAC.require_role(allowed_roles)`, `RBAC.require_scope(user, resource_type, resource_id)`
- **Data flow:** Used as FastAPI dependencies on route handlers. Failure raises `RBAC_001` / `RBAC_002`, which the global handler converts to 403 + audit log entry.

### Import Graph

Forward edges only (every domain module depends *into* `cycles` and/or `accounts`; `cycles` itself has no domain forward-deps except `notifications`).

```
api/v1 ──► (every module below)

domain layer
────────────
templates       ──► cycles, accounts
budget_uploads  ──► cycles, accounts, notifications, _shared
personnel       ──► cycles, accounts, notifications, _shared
shared_costs    ──► cycles, accounts, notifications, _shared
accounts/actuals──► _shared
consolidation   ──► cycles, budget_uploads, personnel, shared_costs, accounts
cycles          ──► notifications              (deadline-reminder dispatch only)
accounts        ──► (no domain deps)
notifications   ──► (no domain deps)
audit           ──► (no domain deps — leaf)
security        ──► audit                      (records auth/RBAC events)
_shared         ──► (no domain deps — leaf; only imports infra/db models)

every domain module also depends on: audit, security
                                      infra/db
infra layer (leaves of the graph)
─────────────────────────────────
audit          ──► infra/db, infra/crypto, core/clock
security       ──► infra/sso, infra/db, infra/crypto, core/clock
notifications  ──► infra/email, infra/db, core/clock
accounts       ──► infra/db, infra/tabular, infra/storage
templates      ──► infra/excel, infra/storage, infra/db
budget_uploads ──► infra/excel, infra/storage, infra/db (helpers.next_version)
personnel      ──► infra/tabular, infra/storage, infra/db (helpers.next_version)
shared_costs   ──► infra/tabular, infra/storage, infra/db (helpers.next_version)
consolidation  ──► infra/db, infra/jobs, infra/excel, infra/storage
cycles         ──► infra/db, infra/scheduler

infra/tabular  ──► infra/csv_io, infra/excel       (thin dispatcher)
```

**Acyclicity proof (by reverse topological visit):**

| Order | Module | Depends on (already visited) |
|---|---|---|
| 0 | `core/clock`, `core/errors`, `core/logging` | — |
| 0 | `infra/db`, `infra/crypto`, `infra/storage`, `infra/excel`, `infra/csv_io`, `infra/email`, `infra/sso`, `infra/scheduler`, `infra/jobs` | — |
| 0 | `infra/tabular` | infra/csv_io, infra/excel |
| 1 | `domain/_shared` | infra/db (models only) |
| 1 | `audit` | infra leaves, core/clock |
| 2 | `security` | audit, infra |
| 3 | `notifications` | audit, infra |
| 4 | `accounts` | audit, security, _shared, infra |
| 5 | `cycles` | notifications, audit, security, infra |
| 6 | `templates` | cycles, accounts, audit, security, infra |
| 6 | `budget_uploads` | cycles, accounts, notifications, audit, security, _shared, infra |
| 6 | `personnel` | cycles, accounts, notifications, audit, security, _shared, infra |
| 6 | `shared_costs` | cycles, accounts, notifications, audit, security, _shared, infra |
| 7 | `consolidation` | cycles, budget_uploads, personnel, shared_costs, accounts, audit, security, infra |
| 8 | `api/v1` | all of the above |

✅ Every module's dependencies appear strictly earlier in the order. No cycles.

**Critical-path module:** `cycles` (M1) — its `open()` operation transitions the system into the active phase and is the trigger for templates + notifications. It is also the largest module by FR count (5 FRs).

**Module size warnings:**
- **M1 `cycles`** (5 FRs) — approaches the 500-line file limit. Split plan (if needed during impl): extract `dispatch_deadline_reminders` and reminder-schedule logic into `cycles/reminders.py`; keep `cycles/service.py` for create/open/close/reopen. Public exports unchanged.
- **M7 `consolidation`** (4 FRs) — split plan: `consolidation/dashboard.py` (FR-014), `consolidation/report.py` (FR-015, FR-016), `consolidation/export.py` (FR-017 + handler). Public exports unchanged.

**Module Rules:**
- Each module owns its FRs completely
- Cross-module calls go through the `Exports` column above; never reach into another module's internals
- Side effects respect the §3 Side-Effect Ownership table
- `api` (M11) is a pure orchestrator: no business logic, no math, no parsing, no path construction

---

## 5. Contracts

REST endpoints, grouped by resource. Every endpoint maps to exactly one module from §4.

- **Base path:** `/api/v1`
- **Auth:** All endpoints except `/auth/sso/*` require an active session cookie (FR-021); RBAC enforcement noted per endpoint (FR-022).
- **Common error envelope:** see §3 Response Format
- **Common headers:** `X-Request-ID` (server-set, returned to caller), `X-CSRF-Token` (required on all state-changing requests)
- **Pagination:** `?page=N&size=M` for list endpoints; default 50, max 200; response wraps in `{ items: [...], total, page, size }`
- **Datetimes:** ISO-8601 UTC

### 5.1 Auth (M10 `security`)

| Method | Route | FR | Module | Purpose |
|---|---|---|---|---|
| GET | `/api/v1/auth/sso/login?return_to=/path` | FR-021 | M10 | 302 redirect to IdP authorization endpoint |
| GET | `/api/v1/auth/sso/callback` | FR-021 | M10 | OIDC/SAML callback; on success sets `bc_session`, `bc_refresh`, `bc_csrf` cookies and 302 to `return_to` |
| POST | `/api/v1/auth/refresh` | FR-021 | M10 | Refreshes session cookie. **Errors:** `AUTH_004` (refresh expired) → 401 |
| POST | `/api/v1/auth/logout` | FR-021 | M10 | Invalidates session, clears cookies. 204 |
| GET | `/api/v1/auth/me` | FR-021, FR-022 | M10 | Returns current user. **Response 200:** `{ id, name, email, roles: [...], scoped_org_unit_ids: [...] }` |

**Errors emitted by group:** `AUTH_001` (IdP unreachable, 503), `AUTH_002` (callback signature invalid, 400), `AUTH_003` (user not authorized — no role mapping, 403), `AUTH_004` (session/refresh expired, 401).

### 5.2 Cycles (M1 `cycles`)

| Method | Route | FR | Module | Purpose |
|---|---|---|---|---|
| POST | `/api/v1/cycles` | FR-001 | M1 | Create draft cycle. **Request:** `{ fiscal_year: int, deadline: date, reporting_currency: str }`. **Response 201:** `Cycle`. **Errors:** `CYCLE_001` (year already has active cycle, 409). **Roles:** SystemAdmin, FinanceAdmin |
| GET | `/api/v1/cycles` | FR-001, FR-004 | M1 | List cycles (filter `?status=`). **Roles:** any authenticated |
| GET | `/api/v1/cycles/{cycle_id}` | FR-001 | M1 | Get cycle detail |
| GET | `/api/v1/cycles/{cycle_id}/filing-units` | FR-002 | M1 | List filing units (4000–0500) for the cycle with `has_manager` flag and warnings array. **Response 200:** `{ items: [{ org_unit_id, code, name, has_manager, warnings: [...] }], blocking_warnings: int }` |
| POST | `/api/v1/cycles/{cycle_id}/open` | FR-003, FR-009 | M1 | Transition Draft → Open. Triggers template generation + notification batch. **Response 200:** `{ cycle, template_results: [...], notification_batch_id }`. **Errors:** `CYCLE_002` (filing unit missing manager, 409), `CYCLE_003` (not in Draft, 409). **Roles:** FinanceAdmin |
| PATCH | `/api/v1/cycles/{cycle_id}/reminders` | FR-005 | M1 | Set reminder schedule. **Request:** `{ days_before: [7, 3, 1] }`. **Roles:** FinanceAdmin |
| POST | `/api/v1/cycles/{cycle_id}/close` | FR-006 | M1 | Open → Closed. **Roles:** FinanceAdmin |
| POST | `/api/v1/cycles/{cycle_id}/reopen` | FR-006 | M1 | Reopen within window (e.g. ≤ 7 days). **Request:** `{ reason: str }`. **Errors:** `CYCLE_005` (window expired, 409). **Roles:** SystemAdmin |

### 5.3 Accounts & Actuals (M2 `accounts`)

| Method | Route | FR | Module | Purpose |
|---|---|---|---|---|
| GET | `/api/v1/accounts` | FR-007 | M2 | List account codes (filter `?category=operational|personnel|shared_cost`) |
| POST | `/api/v1/accounts` | FR-007 | M2 | Create. **Request:** `{ code, name, category, level }`. **Roles:** SystemAdmin |
| PATCH | `/api/v1/accounts/{id}` | FR-007 | M2 | Update. **Roles:** SystemAdmin |
| POST | `/api/v1/cycles/{cycle_id}/actuals/import` | FR-008 | M2 | Bulk import actuals (multipart upload, CSV/Excel). **Errors:** `ACCOUNT_002` (row invalid, 400 with row-level details). **Roles:** SystemAdmin, FinanceAdmin |
| GET | `/api/v1/cycles/{cycle_id}/actuals` | FR-008 | M2 | Query actuals (filter `?org_unit_id=&account_code=`) |

### 5.4 Templates (M3 `templates`)

| Method | Route | FR | Module | Purpose |
|---|---|---|---|---|
| POST | `/api/v1/cycles/{cycle_id}/templates/regenerate` | FR-009 | M3 | Bulk regenerate failed templates. **Response 200:** `{ results: [{ org_unit_id, status, error? }] }`. **Roles:** FinanceAdmin |
| POST | `/api/v1/cycles/{cycle_id}/org-units/{org_unit_id}/templates/regenerate` | FR-009 | M3 | Regenerate one. **Roles:** FinanceAdmin |
| GET | `/api/v1/cycles/{cycle_id}/org-units/{org_unit_id}/templates/download` | FR-010 | M3 | Stream the template `.xlsx`. **Errors:** `TPL_002` (template not generated yet, 404), `RBAC_002` (not your unit, 403). **Roles:** any role with scope including the org unit |

(Initial template generation is invoked by `POST /cycles/{id}/open` — FR-009 — not by a separate endpoint.)

### 5.5 Budget Uploads (M4 `budget_uploads`)

#### POST `/api/v1/cycles/{cycle_id}/org-units/{org_unit_id}/budget-uploads`
- **FR:** FR-011, FR-013
- **Module:** M4 `budget_uploads`
- **Roles:** Filing-unit manager whose scope includes `org_unit_id`
- **Request:** `multipart/form-data`, field `file` = `.xlsx` (≤10 MB)
- **Response 201:** `BudgetUpload` `{ id, cycle_id, org_unit_id, version, file_hash, uploaded_at, status: "valid" }`
- **Errors:**
  - 400 `UPLOAD_001` — file too large (>10 MB)
  - 400 `UPLOAD_002` — row count exceeds 5000
  - 400 `UPLOAD_007` — batch validation failed; details:
    ```json
    { "error": { "code": "UPLOAD_007", "message": "...",
      "details": [
        { "row": 12, "column": "dept_code", "code": "UPLOAD_003", "reason": "..." },
        { "row": 15, "column": "amount", "code": "UPLOAD_005", "reason": "..." }
      ] } }
    ```
  - 409 `CYCLE_004` — cycle not Open
  - 403 `RBAC_002` — not authorized for this org unit

| Method | Route | FR | Module | Purpose |
|---|---|---|---|---|
| GET | `/api/v1/cycles/{cycle_id}/org-units/{org_unit_id}/budget-uploads` | FR-012 | M4 | List versions for org unit (newest first) |
| GET | `/api/v1/budget-uploads/{upload_id}` | FR-012 | M4 | Version detail |
| GET | `/api/v1/budget-uploads/{upload_id}/file` | FR-012 | M4 | Download original file (audited) |
| POST | `/api/v1/budget-uploads/{upload_id}/notifications/resend` | FR-013 | M4 | Resend the upload-confirmation email. **Roles:** FinanceAdmin or uploader |

### 5.6 Personnel Budget Imports (M5 `personnel`)

#### POST `/api/v1/cycles/{cycle_id}/personnel-budgets`
- **FR:** FR-024, FR-026
- **Module:** M5 `personnel`
- **Roles:** HRAdmin
- **Request:** `multipart/form-data`, field `file` = `.csv` or `.xlsx` with columns `dept_id, account_code, amount`
- **Response 201:** `PersonnelBudgetUpload` `{ id, cycle_id, version, row_count, uploaded_at, status: "valid" }`. Side effect: Email notification to FinanceAdmin.
- **Errors:**
  - 400 `PERS_004` — batch validation failed; row-level details:
    ```json
    { "error": { "code": "PERS_004", "message": "...",
      "details": [
        { "row": 7, "code": "PERS_001", "reason": "dept_id 4023 not found in org tree" },
        { "row": 11, "code": "PERS_002", "reason": "account 6101 is not personnel category" },
        { "row": 14, "code": "PERS_003", "reason": "amount must be positive" }
      ] } }
    ```
  - 409 `CYCLE_004` — cycle closed

| Method | Route | FR | Module | Purpose |
|---|---|---|---|---|
| GET | `/api/v1/cycles/{cycle_id}/personnel-budgets` | FR-025 | M5 | List versions |
| GET | `/api/v1/personnel-budgets/{upload_id}` | FR-025 | M5 | Version detail (header + summary) |
| GET | `/api/v1/personnel-budgets/{upload_id}/file` | FR-025 | M5 | Download original file (audited) |

### 5.7 Shared Cost Imports (M6 `shared_costs`)

#### POST `/api/v1/cycles/{cycle_id}/shared-costs`
- **FR:** FR-027, FR-029
- **Module:** M6 `shared_costs`
- **Roles:** FinanceAdmin
- **Request:** identical shape to personnel-budgets POST
- **Response 201:** `SharedCostUpload` (same shape). Side effect: Email to managers of affected org units (computed by `diff_affected_units`).
- **Errors:** 400 `SHARED_004` (batch validation, with row-level `SHARED_001/002/003`); 409 `CYCLE_004`

| Method | Route | FR | Module | Purpose |
|---|---|---|---|---|
| GET | `/api/v1/cycles/{cycle_id}/shared-costs` | FR-028 | M6 | List versions |
| GET | `/api/v1/shared-costs/{upload_id}` | FR-028 | M6 | Version detail (includes `affected_org_units` summary) |
| GET | `/api/v1/shared-costs/{upload_id}/file` | FR-028 | M6 | Download original |

### 5.8 Dashboard (M7 `consolidation`)

#### GET `/api/v1/cycles/{cycle_id}/dashboard`
- **FR:** FR-014
- **Module:** M7 `consolidation`
- **Roles:** any authenticated; result is auto-scoped by `RBAC.scoped_org_units(user)`
- **Query params:** `?status=not_downloaded|downloaded|uploaded|resubmit_requested`, `?sort=`, `?page=&size=`
- **Response 200:**
  ```json
  {
    "cycle": { "id": "...", "fiscal_year": 2026, "status": "open", "deadline": "..." },
    "items": [
      { "org_unit_id": "...", "code": "4023", "name": "...",
        "status": "uploaded", "latest_version": 3,
        "latest_uploaded_at": "...", "uploader": "..." }
    ],
    "summary": { "total": 120, "uploaded": 87, "not_downloaded": 12, "downloaded": 18, "resubmit_requested": 3 },
    "data_freshness": { "snapshot_at": "...", "stale": false }
  }
  ```
- **Notes:** 0000公司 Reviewer receives `items: []` and only the consolidated-report link (per FR-014). Dashboard polls every ≤5s on the frontend; `stale: true` when backend cannot refresh and returns last known snapshot.

### 5.9 Consolidated Reports (M7 `consolidation`)

#### GET `/api/v1/cycles/{cycle_id}/reports/consolidated`
- **FR:** FR-015, FR-016
- **Module:** M7 `consolidation`
- **Roles:** any authenticated; auto-scoped
- **Query params:** `?level=` (optional filter to specific org-unit subtree)
- **Response 200:**
  ```json
  {
    "cycle_id": "...",
    "scope": { "org_unit_ids": [...] },
    "rows": [
      {
        "org_unit": { "id": "...", "code": "1023", "name": "..." },
        "account": { "code": "5101", "name": "...", "category": "operational" },
        "operational_budget": 1200000,
        "personnel_budget": null,
        "shared_cost": null,
        "actual": 1100000,
        "delta_amount": 100000,
        "delta_pct": "9.1",
        "budget_status": "uploaded"
      }
    ],
    "data_sources": {
      "operational": { "last_updated_at": "...", "version_count": 87 },
      "personnel":   { "last_updated_at": "...", "version": 4 },
      "shared_cost": { "last_updated_at": "...", "version": 2 }
    }
  }
  ```
- **Notes:** Personnel + shared_cost columns are populated only for org units at level 1000處 or above (per FR-015 / PRD §8.3). `delta_pct` is `"N/A"` when `actual` is 0; `budget_status: "not_uploaded"` when no budget upload exists yet.

| Method | Route | FR | Module | Purpose |
|---|---|---|---|---|
| POST | `/api/v1/cycles/{cycle_id}/reports/exports` | FR-017 | M7 | Enqueue async export. **Request:** `{ format: "xlsx"|"pdf", scope?: {...} }`. **Response 202:** `{ job_id }`. Small reports (≤1000 units) may execute synchronously and return 201 with file URL. |
| GET | `/api/v1/reports/exports/{job_id}` | FR-017 | M7 | Job status `{ id, status: "queued"|"running"|"succeeded"|"failed", error?, file_url? }` |
| GET | `/api/v1/reports/exports/{job_id}/file` | FR-017 | M7 | Download exported file. **Errors:** `REPORT_002` (export failed, 410) |

### 5.10 Notifications & Resubmit (M8 `notifications`)

| Method | Route | FR | Module | Purpose |
|---|---|---|---|---|
| POST | `/api/v1/cycles/{cycle_id}/org-units/{org_unit_id}/resubmit-requests` | FR-018 | M8 | Trigger resubmit. **Request:** `{ reason: str, target_version?: int }`. **Response 201:** `ResubmitRequest`. Side effect: email + dashboard flag. **Errors:** `NOTIFY_002` (record-write failed → notification NOT sent, 500). **Roles:** FinanceAdmin or upline reviewer with scope |
| GET | `/api/v1/cycles/{cycle_id}/org-units/{org_unit_id}/resubmit-requests` | FR-019 | M8 | List history for unit |
| GET | `/api/v1/notifications` | FR-013, FR-018, FR-020, FR-026 | M8 | List notifications (filter `?status=failed&type=`) for ops monitoring |
| POST | `/api/v1/notifications/{id}/resend` | FR-013 | M8 | Resend a failed notification. **Roles:** FinanceAdmin |

(FR-005 deadline-reminder cron is internal — no user-facing endpoint. FR-020 is the same job; recipients are automatic.)

### 5.11 Audit (M9 `audit`)

| Method | Route | FR | Module | Purpose |
|---|---|---|---|---|
| GET | `/api/v1/audit-logs` | FR-023 | M9 | Query with filters: `?user_id=&action=&resource_type=&from=&to=&page=&size=`. **Response 200:** `{ items: [{ id, timestamp, user_id, action, resource_type, resource_id, ip_address, details }], total }`. **Roles:** ITSecurityAuditor |
| GET | `/api/v1/audit-logs/verify` | FR-023 | M9 | Verify hash chain `?from=&to=`. **Response 200:** `{ verified: true, range: [...], chain_length: N }`. **Errors:** `AUDIT_001` (chain broken, 500). **Roles:** ITSecurityAuditor |
| GET | `/api/v1/audit-logs/export` | FR-023 | M9 | CSV export of filtered range. **Roles:** ITSecurityAuditor |

### 5.12 Admin — Org Units & Users (M1 + M10)

These endpoints support FR-002 (org tree must be correct before cycle open) and FR-022 (role assignment).

| Method | Route | FR | Module | Purpose |
|---|---|---|---|---|
| GET | `/api/v1/admin/org-units` | FR-002 | M1 | Get full org tree |
| POST | `/api/v1/admin/org-units` | FR-002 | M1 | Create. **Request:** `{ code, name, parent_id, is_filing_unit, is_reviewer_only }`. **Roles:** SystemAdmin |
| PATCH | `/api/v1/admin/org-units/{id}` | FR-002 | M1 | Update |
| DELETE | `/api/v1/admin/org-units/{id}` | FR-002 | M1 | Delete (only when no historical references). **Roles:** SystemAdmin |
| GET | `/api/v1/admin/users` | FR-022 | M10 | List users (filter by role/org-unit) |
| PATCH | `/api/v1/admin/users/{id}/roles` | FR-022 | M10 | Update role + scope. **Roles:** SystemAdmin |

### Frontend Screen Responsibilities (informational, not REST contracts)

For implementation guidance — each screen consumes one or more endpoints above.

| Screen | Page Path | Role(s) | Endpoints Used | FR |
|---|---|---|---|---|
| SSO Login Landing | `/` | unauthenticated | `/auth/sso/login` | FR-021 |
| Filing-Unit Upload | `/upload` | Filing-Unit Manager | `/auth/me`, `/cycles/{id}/org-units/{ou}/templates/download`, `/cycles/{id}/org-units/{ou}/budget-uploads` | FR-010, 011, 012 |
| Dashboard | `/dashboard` | FinanceAdmin, Reviewers | `/cycles/{id}/dashboard` (poll ≤5s) | FR-004, 014 |
| Consolidated Report | `/reports` | FinanceAdmin, Reviewers, 0000公司 Reviewer | `/cycles/{id}/reports/consolidated`, `/cycles/{id}/reports/exports` | FR-015, 016, 017 |
| HR Personnel Import | `/personnel-import` | HRAdmin | `/cycles/{id}/personnel-budgets` (POST + GET) | FR-024, 025, 026 |
| Shared Cost Import | `/shared-cost-import` | FinanceAdmin | `/cycles/{id}/shared-costs` (POST + GET) | FR-027, 028, 029 |
| Cycle Admin | `/admin/cycles` | FinanceAdmin, SystemAdmin | `/cycles` CRUD + `/cycles/{id}/open|close|reopen|reminders` | FR-001, 003, 005, 006 |
| Account Master | `/admin/accounts` | SystemAdmin | `/accounts` CRUD, `/cycles/{id}/actuals/import` | FR-007, 008 |
| Org Tree Admin | `/admin/org-units` | SystemAdmin | `/admin/org-units` CRUD | FR-002 |
| Resubmit Trigger | (modal in Dashboard) | FinanceAdmin, Reviewers | `/cycles/{id}/org-units/{ou}/resubmit-requests` | FR-018, 019 |
| Audit Log Search | `/audit` | ITSecurityAuditor | `/audit-logs`, `/audit-logs/verify`, `/audit-logs/export` | FR-023 |

---

## 6. Database Schema

Generated from PRD Section 10 (15 entities) plus 3 supporting tables required by the architecture (`sessions`, `job_runs`, `cycle_reminder_schedules`). PostgreSQL 16 dialect.

**Conventions:**
- UUID v4 primary keys via `gen_random_uuid()` (`pgcrypto` extension; **hashing only** — no symmetric encryption, see §1)
- All timestamps `TIMESTAMPTZ`, stored UTC
- Encrypted columns use `BYTEA` for AES-256-GCM ciphertext; encryption performed by `infra/crypto` **before INSERT** (never via `pgcrypto`)
- Foreign keys: `ON DELETE RESTRICT` by default; `ON DELETE CASCADE` only on owned line tables (`budget_lines` etc.) where deleting the header MUST drop its lines
- All entity tables have `created_at` and `updated_at`; `updated_at` is maintained by an `updated_at_trigger` (created once, applied per table)
- 5-year retention (NFR-SEC-003) is enforced by an offline retention job, not at the schema level — schema preserves rows indefinitely

```sql
-- =====================================================================
-- Extensions
-- =====================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid() + hash helpers ONLY
                                          -- AES is performed in infra/crypto, never here

-- =====================================================================
-- Shared updated_at trigger
-- =====================================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =====================================================================
-- Enums
-- =====================================================================
CREATE TYPE cycle_status AS ENUM ('draft', 'open', 'closed');
CREATE TYPE upload_status AS ENUM ('pending', 'valid', 'invalid');
CREATE TYPE notification_type AS ENUM (
  'cycle_opened', 'upload_confirmed', 'resubmit_requested',
  'deadline_reminder', 'personnel_imported', 'shared_cost_imported'
);
CREATE TYPE notification_status AS ENUM ('queued', 'sent', 'failed', 'bounced');
CREATE TYPE notification_channel AS ENUM ('email');
CREATE TYPE account_category AS ENUM ('operational', 'personnel', 'shared_cost');
CREATE TYPE org_level_code AS ENUM ('0000','0500','0800','1000','2000','4000','5000','6000');
CREATE TYPE job_status AS ENUM ('queued', 'running', 'succeeded', 'failed');

-- =====================================================================
-- OrgUnit
-- Entity: PRD §10 OrgUnit | FRs: FR-002, FR-022
-- =====================================================================
CREATE TABLE org_units (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code          VARCHAR(32) NOT NULL UNIQUE,                  -- e.g. "4023"
  name          VARCHAR(200) NOT NULL,
  level_code    org_level_code NOT NULL,                      -- 6000~0000
  parent_id     UUID REFERENCES org_units(id) ON DELETE RESTRICT,
  is_filing_unit     BOOLEAN NOT NULL DEFAULT FALSE,          -- 4000~0500 by rule
  is_reviewer_only   BOOLEAN NOT NULL DEFAULT FALSE,          -- 0000公司 only
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (NOT (is_filing_unit AND is_reviewer_only))
);
CREATE INDEX idx_org_units_parent ON org_units(parent_id);
CREATE INDEX idx_org_units_filing ON org_units(is_filing_unit) WHERE is_filing_unit;
CREATE TRIGGER trg_org_units_updated BEFORE UPDATE ON org_units
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =====================================================================
-- User
-- Entity: PRD §10 User | FRs: FR-021, FR-022
-- email + sso_id are encrypted at rest (PRD §7 資料保護)
-- =====================================================================
CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sso_id_enc      BYTEA NOT NULL,                             -- AES-GCM ciphertext
  sso_id_hash     BYTEA NOT NULL UNIQUE,                      -- HMAC-SHA256 for lookup
  name            VARCHAR(200) NOT NULL,
  email_enc       BYTEA NOT NULL,                             -- AES-GCM ciphertext
  email_hash      BYTEA NOT NULL UNIQUE,
  roles           JSONB NOT NULL DEFAULT '[]'::jsonb,         -- e.g. ["FinanceAdmin"]
  org_unit_id     UUID REFERENCES org_units(id) ON DELETE RESTRICT,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_org_unit ON users(org_unit_id);
CREATE INDEX idx_users_roles_gin ON users USING gin (roles);
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =====================================================================
-- Sessions (architecture-added; cookie-backed sessions per §3 Session table)
-- FRs: FR-021, NFR-SEC-002
-- =====================================================================
CREATE TABLE sessions (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  refresh_token_hash  BYTEA NOT NULL UNIQUE,                  -- HMAC of refresh JWT
  csrf_token          VARCHAR(64) NOT NULL,
  ip_address          INET,
  user_agent          TEXT,
  last_activity_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  absolute_expires_at TIMESTAMPTZ NOT NULL,                   -- 8h from creation
  revoked_at          TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_active ON sessions(absolute_expires_at)
  WHERE revoked_at IS NULL;

-- =====================================================================
-- AccountCode
-- Entity: PRD §10 AccountCode | FRs: FR-007
-- =====================================================================
CREATE TABLE account_codes (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code          VARCHAR(32) NOT NULL UNIQUE,
  name          VARCHAR(200) NOT NULL,
  category      account_category NOT NULL,                    -- operational/personnel/shared_cost
  level         INT NOT NULL CHECK (level >= 1),
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_account_codes_category ON account_codes(category) WHERE is_active;
CREATE TRIGGER trg_account_codes_updated BEFORE UPDATE ON account_codes
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =====================================================================
-- BudgetCycle
-- Entity: PRD §10 BudgetCycle | FRs: FR-001, FR-003, FR-006
-- =====================================================================
CREATE TABLE budget_cycles (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fiscal_year        INT NOT NULL,
  deadline           DATE NOT NULL,
  reporting_currency CHAR(3) NOT NULL DEFAULT 'TWD',
  status             cycle_status NOT NULL DEFAULT 'draft',
  opened_at          TIMESTAMPTZ,
  closed_at          TIMESTAMPTZ,
  closed_by          UUID REFERENCES users(id),
  reopen_reason      TEXT,
  reopened_at        TIMESTAMPTZ,
  created_by         UUID NOT NULL REFERENCES users(id),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Only one non-closed cycle per fiscal year (FR-001)
CREATE UNIQUE INDEX uq_budget_cycles_active_year
  ON budget_cycles(fiscal_year)
  WHERE status IN ('draft', 'open');
CREATE INDEX idx_budget_cycles_status ON budget_cycles(status);
CREATE TRIGGER trg_budget_cycles_updated BEFORE UPDATE ON budget_cycles
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =====================================================================
-- CycleReminderSchedule (architecture-added; FR-005)
-- =====================================================================
CREATE TABLE cycle_reminder_schedules (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cycle_id      UUID NOT NULL REFERENCES budget_cycles(id) ON DELETE CASCADE,
  days_before   INT NOT NULL CHECK (days_before > 0),         -- e.g. 7, 3, 1
  last_run_at   TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (cycle_id, days_before)
);
CREATE INDEX idx_reminder_schedules_cycle ON cycle_reminder_schedules(cycle_id);

-- =====================================================================
-- ActualExpense
-- Entity: PRD §10 ActualExpense | FRs: FR-008
-- =====================================================================
CREATE TABLE actual_expenses (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cycle_id        UUID NOT NULL REFERENCES budget_cycles(id) ON DELETE RESTRICT,
  org_unit_id     UUID NOT NULL REFERENCES org_units(id) ON DELETE RESTRICT,
  account_code_id UUID NOT NULL REFERENCES account_codes(id) ON DELETE RESTRICT,
  amount          NUMERIC(18,2) NOT NULL,
  imported_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  imported_by     UUID NOT NULL REFERENCES users(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (cycle_id, org_unit_id, account_code_id)
);
CREATE INDEX idx_actuals_cycle_org ON actual_expenses(cycle_id, org_unit_id);
CREATE TRIGGER trg_actual_expenses_updated BEFORE UPDATE ON actual_expenses
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =====================================================================
-- ExcelTemplate
-- Entity: PRD §10 ExcelTemplate | FRs: FR-009, FR-010
-- file_path is encrypted (avoids leaking org structure if DB is exfiltrated)
-- =====================================================================
CREATE TABLE excel_templates (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cycle_id        UUID NOT NULL REFERENCES budget_cycles(id) ON DELETE CASCADE,
  org_unit_id     UUID NOT NULL REFERENCES org_units(id) ON DELETE RESTRICT,
  file_path_enc   BYTEA NOT NULL,                             -- AES-GCM
  file_hash       BYTEA NOT NULL,                             -- sha256(bytes)
  generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  generated_by    UUID NOT NULL REFERENCES users(id),
  download_count  INT NOT NULL DEFAULT 0,
  generation_error TEXT,                                      -- non-null when generation failed
  UNIQUE (cycle_id, org_unit_id)
);
CREATE INDEX idx_templates_cycle ON excel_templates(cycle_id);

-- =====================================================================
-- BudgetUpload
-- Entity: PRD §10 BudgetUpload | FRs: FR-011, FR-012
-- =====================================================================
CREATE TABLE budget_uploads (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cycle_id        UUID NOT NULL REFERENCES budget_cycles(id) ON DELETE RESTRICT,
  org_unit_id     UUID NOT NULL REFERENCES org_units(id) ON DELETE RESTRICT,
  uploader_id     UUID NOT NULL REFERENCES users(id),
  version         INT NOT NULL,                                -- monotonic per (cycle, org_unit)
  file_path_enc   BYTEA NOT NULL,
  file_hash       BYTEA NOT NULL,
  file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes <= 10485760),
  row_count       INT NOT NULL CHECK (row_count <= 5000),
  status          upload_status NOT NULL DEFAULT 'valid',
  uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (cycle_id, org_unit_id, version)
);
CREATE INDEX idx_budget_uploads_cycle_unit ON budget_uploads(cycle_id, org_unit_id, version DESC);
-- "latest version per (cycle, org_unit)" lookup support
CREATE INDEX idx_budget_uploads_latest ON budget_uploads(cycle_id, org_unit_id, uploaded_at DESC);

-- =====================================================================
-- BudgetLine
-- Entity: PRD §10 BudgetLine | FRs: FR-011, FR-015
-- =====================================================================
CREATE TABLE budget_lines (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  upload_id       UUID NOT NULL REFERENCES budget_uploads(id) ON DELETE CASCADE,
  account_code_id UUID NOT NULL REFERENCES account_codes(id) ON DELETE RESTRICT,
  amount          NUMERIC(18,2) NOT NULL CHECK (amount >= 0),
  UNIQUE (upload_id, account_code_id)
);
CREATE INDEX idx_budget_lines_upload ON budget_lines(upload_id);
CREATE INDEX idx_budget_lines_account ON budget_lines(account_code_id);

-- =====================================================================
-- PersonnelBudgetUpload + Line
-- Entity: PRD §10 PersonnelBudgetUpload, PersonnelBudgetLine
-- FRs: FR-024, FR-025
-- =====================================================================
CREATE TABLE personnel_budget_uploads (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cycle_id        UUID NOT NULL REFERENCES budget_cycles(id) ON DELETE RESTRICT,
  uploader_id     UUID NOT NULL REFERENCES users(id),
  version         INT NOT NULL,
  file_path_enc   BYTEA NOT NULL,
  file_hash       BYTEA NOT NULL,
  status          upload_status NOT NULL DEFAULT 'valid',
  affected_org_units_summary JSONB,                            -- list of org_unit_ids changed
  uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (cycle_id, version)
);
CREATE INDEX idx_personnel_uploads_cycle ON personnel_budget_uploads(cycle_id, version DESC);

CREATE TABLE personnel_budget_lines (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  upload_id       UUID NOT NULL REFERENCES personnel_budget_uploads(id) ON DELETE CASCADE,
  org_unit_id     UUID NOT NULL REFERENCES org_units(id) ON DELETE RESTRICT,
  account_code_id UUID NOT NULL REFERENCES account_codes(id) ON DELETE RESTRICT,
  amount          NUMERIC(18,2) NOT NULL CHECK (amount > 0),
  UNIQUE (upload_id, org_unit_id, account_code_id)
);
CREATE INDEX idx_personnel_lines_upload ON personnel_budget_lines(upload_id);
CREATE INDEX idx_personnel_lines_org ON personnel_budget_lines(org_unit_id);

-- =====================================================================
-- SharedCostUpload + Line
-- Entity: PRD §10 SharedCostUpload, SharedCostLine
-- FRs: FR-027, FR-028
-- =====================================================================
CREATE TABLE shared_cost_uploads (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cycle_id        UUID NOT NULL REFERENCES budget_cycles(id) ON DELETE RESTRICT,
  uploader_id     UUID NOT NULL REFERENCES users(id),
  version         INT NOT NULL,
  file_path_enc   BYTEA NOT NULL,
  file_hash       BYTEA NOT NULL,
  status          upload_status NOT NULL DEFAULT 'valid',
  affected_org_units_summary JSONB,
  uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (cycle_id, version)
);
CREATE INDEX idx_shared_uploads_cycle ON shared_cost_uploads(cycle_id, version DESC);

CREATE TABLE shared_cost_lines (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  upload_id       UUID NOT NULL REFERENCES shared_cost_uploads(id) ON DELETE CASCADE,
  org_unit_id     UUID NOT NULL REFERENCES org_units(id) ON DELETE RESTRICT,
  account_code_id UUID NOT NULL REFERENCES account_codes(id) ON DELETE RESTRICT,
  amount          NUMERIC(18,2) NOT NULL CHECK (amount > 0),
  UNIQUE (upload_id, org_unit_id, account_code_id)
);
CREATE INDEX idx_shared_lines_upload ON shared_cost_lines(upload_id);
CREATE INDEX idx_shared_lines_org ON shared_cost_lines(org_unit_id);

-- =====================================================================
-- ResubmitRequest
-- Entity: PRD §10 ResubmitRequest | FRs: FR-018, FR-019
-- =====================================================================
CREATE TABLE resubmit_requests (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cycle_id        UUID NOT NULL REFERENCES budget_cycles(id) ON DELETE RESTRICT,
  org_unit_id     UUID NOT NULL REFERENCES org_units(id) ON DELETE RESTRICT,
  requester_id    UUID NOT NULL REFERENCES users(id),
  target_version  INT,                                         -- the version flagged
  reason          TEXT NOT NULL,
  requested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_resubmit_cycle_org ON resubmit_requests(cycle_id, org_unit_id, requested_at DESC);

-- =====================================================================
-- Notification
-- Entity: PRD §10 Notification | FRs: FR-013, FR-018, FR-020, FR-026, FR-029
-- =====================================================================
CREATE TABLE notifications (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recipient_id    UUID NOT NULL REFERENCES users(id),
  type            notification_type NOT NULL,
  channel         notification_channel NOT NULL DEFAULT 'email',
  status          notification_status NOT NULL DEFAULT 'queued',
  related_resource_type VARCHAR(64),
  related_resource_id   UUID,
  link_url        TEXT,
  subject         VARCHAR(500),
  body_excerpt    TEXT,
  bounce_reason   TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  sent_at         TIMESTAMPTZ
);
CREATE INDEX idx_notifications_recipient ON notifications(recipient_id, created_at DESC);
CREATE INDEX idx_notifications_status ON notifications(status) WHERE status IN ('queued','failed','bounced');

-- =====================================================================
-- AuditLog (FR-023)
-- Append-only enforced at app layer; hash chain provides tamper evidence
-- =====================================================================
CREATE TABLE audit_logs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sequence_no         BIGSERIAL NOT NULL UNIQUE,               -- ordered chain index
  user_id             UUID REFERENCES users(id),               -- nullable for unauthenticated events
  action              VARCHAR(64) NOT NULL,
  resource_type       VARCHAR(64) NOT NULL,
  resource_id         UUID,
  ip_address          INET,
  details             JSONB NOT NULL DEFAULT '{}'::jsonb,
  prev_hash           BYTEA NOT NULL,                          -- hash of previous row
  hash_chain_value    BYTEA NOT NULL,                          -- hash(prev || row payload)
  occurred_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_user ON audit_logs(user_id, occurred_at DESC);
CREATE INDEX idx_audit_action ON audit_logs(action, occurred_at DESC);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_occurred ON audit_logs(occurred_at);
-- App-layer enforced; explicit DB-level guard against UPDATE/DELETE:
REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC;
-- (grant SELECT/INSERT to the application role only via deploy script)

-- =====================================================================
-- JobRun (architecture-added; durable async jobs — FR-017)
-- =====================================================================
CREATE TABLE job_runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_type        VARCHAR(64) NOT NULL,                       -- e.g. "export_consolidated_report"
  status          job_status NOT NULL DEFAULT 'queued',
  payload         JSONB NOT NULL,
  result          JSONB,
  result_file_path_enc BYTEA,                                 -- AES-GCM if file produced
  error_message   TEXT,
  enqueued_by     UUID REFERENCES users(id),
  enqueued_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at      TIMESTAMPTZ,
  finished_at     TIMESTAMPTZ,
  attempts        INT NOT NULL DEFAULT 0,
  worker_id       VARCHAR(128)                                -- claim marker for the worker
);
CREATE INDEX idx_job_runs_queue ON job_runs(status, enqueued_at) WHERE status = 'queued';
CREATE INDEX idx_job_runs_user ON job_runs(enqueued_by, enqueued_at DESC);
```

---

## 7. Environment & Configuration

All variables prefixed `BC_` (Budget Collection). Loaded by `app.config` (Pydantic Settings) from `.env` file or process environment. Pydantic Settings enforces required fields at startup — missing required vars cause an immediate fail-fast crash with a clear error.

### Database

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BC_DATABASE_URL` | Yes | — | Async SQLAlchemy URL: `postgresql+asyncpg://user:pass@host:5432/budget_collection` |
| `BC_DATABASE_POOL_SIZE` | No | `10` | Connection pool size |
| `BC_DATABASE_MAX_OVERFLOW` | No | `5` | Pool overflow connections |

### Cryptography (FR-023, §7 資料保護)

| Variable | Required | Description |
|----------|----------|-------------|
| `BC_CRYPTO_KEY` | Yes | 32-byte master AES-256 key (hex-encoded). Used by `infra/crypto` for column encryption. **Loss of this key = permanent loss of all encrypted columns.** Backed up out-of-band per §7 Backup Contract. |
| `BC_CRYPTO_KEY_ID` | Yes | Identifier of the active key for envelope encryption / future rotation (e.g. `"k-2026-04"`) |
| `BC_AUDIT_HMAC_KEY` | Yes | HMAC key for audit-log hash chain (separate from `BC_CRYPTO_KEY` so rotation is independent) |
| `BC_USER_LOOKUP_HMAC_KEY` | Yes | HMAC key for `users.email_hash` / `users.sso_id_hash` deterministic lookup |

### SSO (FR-021)

| Variable | Required | Description |
|----------|----------|-------------|
| `BC_SSO_PROTOCOL` | Yes | `oidc` or `saml2` |
| `BC_SSO_CLIENT_ID` | Yes | Client/SP identifier registered with the IdP |
| `BC_SSO_CLIENT_SECRET` | Yes (OIDC) | OIDC client secret |
| `BC_SSO_DISCOVERY_URL` | Yes (OIDC) | OIDC discovery endpoint, e.g. `https://idp.corp/.well-known/openid-configuration` |
| `BC_SSO_METADATA_URL` | Yes (SAML) | SAML IdP metadata XML URL |
| `BC_SSO_REDIRECT_URI` | Yes | Application callback URL, e.g. `https://budget.corp/api/v1/auth/sso/callback` |
| `BC_SSO_SCOPES` | No | OIDC scopes, default `openid profile email groups` |
| `BC_SSO_ROLE_CLAIM` | No | JSON path to roles claim, default `groups` |
| `BC_SSO_ROLE_MAPPING` | Yes | JSON object mapping IdP group names to system roles, e.g. `{"BC_FINANCE":"FinanceAdmin","BC_HR":"HRAdmin"}` |

### Sessions (FR-021, NFR-SEC-002)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BC_JWT_SIGNING_KEY` | Yes | — | HMAC-SHA256 key for `bc_session` / `bc_refresh` JWT signing |
| `BC_SESSION_IDLE_MINUTES` | No | `30` | Idle timeout (NFR-SEC-002) |
| `BC_SESSION_ABSOLUTE_HOURS` | No | `8` | Absolute lifetime cap |
| `BC_COOKIE_DOMAIN` | Yes | — | Cookie `Domain=` attribute, e.g. `budget.corp` |
| `BC_COOKIE_SECURE` | No | `true` | Set `Secure` flag (must be `true` in prod) |

### SMTP (FR-013, FR-018, FR-020, FR-026, FR-029)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BC_SMTP_HOST` | Yes | — | Internal SMTP relay hostname |
| `BC_SMTP_PORT` | No | `587` | |
| `BC_SMTP_USE_TLS` | No | `true` | STARTTLS |
| `BC_SMTP_USER` | No | — | Optional auth |
| `BC_SMTP_PASSWORD` | No | — | Optional auth |
| `BC_SMTP_FROM` | Yes | — | From address, e.g. `budget-noreply@corp` |
| `BC_SMTP_REPLY_TO` | No | — | Optional Reply-To |

### Storage (PRD §7 資料保護)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BC_UPLOAD_DIR` | Yes | — | Path to encrypted volume for uploaded Excel/CSV files. Backed up per §7 Backup Contract item #2. |
| `BC_TEMPLATE_DIR` | Yes | — | Generated Excel templates directory |
| `BC_EXPORT_DIR` | Yes | — | Async export output directory |
| `BC_MAX_UPLOAD_BYTES` | No | `10485760` | 10 MB hard limit (FR-011 boundary) |
| `BC_MAX_UPLOAD_ROWS` | No | `5000` | Per-file row limit (FR-011 boundary) |

### Application

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BC_LOG_LEVEL` | No | `INFO` | `DEBUG`/`INFO`/`WARN`/`ERROR` |
| `BC_FRONTEND_ORIGIN` | Yes | — | CORS allow-origin for the React app, e.g. `https://budget.corp` |
| `BC_TIMEZONE` | No | `Asia/Taipei` | Server-side cron evaluation TZ (FR-005 — daily 09:00) |
| `BC_REOPEN_WINDOW_DAYS` | No | `7` | FR-006 reopen window |
| `BC_DEADLINE_REMINDER_CRON` | No | `0 9 * * *` | APScheduler cron expression (FR-005 / FR-020) |
| `BC_ASYNC_EXPORT_THRESHOLD` | No | `1000` | FR-017: requests for >N units route to durable job runner |
| `BC_API_BASE_URL` | Yes | — | Public base URL — used in email links |
| `BC_REQUEST_ID_HEADER` | No | `X-Request-ID` | Header name for request correlation |
| `BC_IP_ALLOWLIST` | No | — | Optional comma-separated CIDRs (PRD §7 網路存取控制) |

### Job Runner (FR-017)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BC_JOBS_WORKER_ID` | Yes (worker) | — | Unique worker process identifier (used for `job_runs.worker_id` claim) |
| `BC_JOBS_POLL_INTERVAL_SECONDS` | No | `5` | Worker polling interval |
| `BC_JOBS_MAX_ATTEMPTS` | No | `3` | Retry attempts before marking failed |

### Frontend (Vite build-time, prefixed `VITE_`)

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_BASE_URL` | Yes | Backend base URL, e.g. `https://budget.corp` |
| `VITE_DEFAULT_LOCALE` | No | Default `zh-TW` |

### Backup Contract (NFR-REL-002 / NFR-REL-003)

**Ownership:** **Enterprise IT** operates the backup product and schedule. This project *defines the contract* (what must be backed up, at what frequency, how to verify a restore) and Enterprise IT *executes* it against that contract. The project team remains responsible for the restore-verification checklist at each drill, since only the application can validate hash-chain integrity and encrypted-column decryption.

**The contract:** A "backup" of this system is **not** just a database dump. A successful restore requires **all four** of the following from the same point in time (or within RPO ≤ 24 h drift):

| # | Asset | Path / Source | Backup Method | Notes |
|---|-------|---------------|---------------|-------|
| 1 | Database | PostgreSQL cluster | `pg_dump` nightly + WAL archiving for PITR (RPO ≤ 24 h) | Includes all 18 tables + audit hash chain. Restore must verify hash-chain continuity post-restore. |
| 2 | Uploaded files | `BC_UPLOAD_DIR` (encrypted volume mount) | rsync / volume snapshot nightly | Holds every BudgetUpload, PersonnelBudgetUpload, SharedCostUpload Excel/CSV file referenced by `file_path_enc`. **Without this, file_path rows in DB become dangling.** |
| 3 | Generated templates | `BC_TEMPLATE_DIR` | rsync / volume snapshot nightly | Reproducible from DB if needed, but backing up avoids re-generation cost on restore. |
| 4 | Application secrets | `.env` on host (filesystem ACL 0600, root only) | Out-of-band, encrypted, stored separately from DB backups (**NEVER** in the same backup job as the DB) | Includes `BC_DATABASE_URL`, `BC_CRYPTO_KEY`, `BC_AUDIT_HMAC_KEY`, `BC_USER_LOOKUP_HMAC_KEY`, `BC_JWT_SIGNING_KEY`, SMTP credentials, SSO client secret. **Loss of `BC_CRYPTO_KEY` = permanent loss of all encrypted columns.** |

**Handoff artifacts to Enterprise IT (deliverable before go-live):**
1. This contract table as a standalone runbook
2. The restore verification checklist (below)
3. A documented procedure for rotating `BC_CRYPTO_KEY` (envelope encryption via `BC_CRYPTO_KEY_ID`)
4. Named contact on the project team who owns each drill

**Restore verification checklist** (run after every restore drill, target ≥ quarterly; executed jointly by Enterprise IT and the project team):
- [ ] Postgres reachable, all migrations at expected revision
- [ ] Random sample of 5 BudgetUpload rows: `file_path_enc` decrypts AND resolves to a real file on disk
- [ ] Audit hash chain validates end-to-end (no broken links) — `GET /api/v1/audit-logs/verify`
- [ ] Decryption round-trip works on a known encrypted column (proves `BC_CRYPTO_KEY` is correct)
- [ ] SSO login succeeds against IdP

**RTO target:** ≤ 4 h (NFR-REL-003) from detected failure to verified restore. Enterprise IT's product and runbook must be able to meet this — the project team will validate the RTO in the first quarterly drill and escalate if it cannot be met.

---

## 8. Testing Strategy

### Test Tiers

Four tiers (backend) + frontend tiers. Tier choice for each test should be the **lowest** that still validates the behavior in question.

| Tier | Type | Scope | Tooling | Speed target | When run |
|------|------|-------|---------|--------------|----------|
| **B1** | Backend Unit | Pure logic — validators, RBAC scope math, hash-chain primitives, delta-pct calculator, account-category filters, reminder-schedule eval, cycle state machine. **No DB, no file I/O.** | pytest + pytest-asyncio | < 10 s total | Every commit |
| **B2** | Backend Component | Single domain module against real Postgres + real `infra/excel`/`infra/csv_io` parsing of fixture files. SMTP + SSO + scheduler are **mocked at the `infra/*` boundary** (not deeper). | pytest + testcontainers-postgres + httpx | < 60 s total | Every commit |
| **B3** | Backend API / Integration | Full FastAPI request → handler → domain → infra → DB. Real Postgres, real file I/O (tmpdir), mocked SMTP + SSO. Covers RBAC, error envelopes, request validation. | pytest + httpx `AsyncClient` against `app` | < 3 min | Every commit |
| **B4** | Backend Performance | NFR-PERF-002 (consolidated report < 15 s for 100 units), Dashboard query latency, hash-chain verify on N=10k rows. Seeded fixture DB. | pytest + `pytest-benchmark`, run on CI nightly + on demand | 2–10 min | Nightly + before release |
| **F1** | Frontend Unit | Pure components, hooks, zod schemas, formatters, RBAC-derived UI predicates | Vitest + React Testing Library | < 10 s | Every commit |
| **F2** | Frontend Component | Single page with mocked TanStack Query responses; verifies state transitions, form validation, error rendering | Vitest + React Testing Library + msw | < 30 s | Every commit |
| **E2E** | End-to-End | Real browser → Vite-served frontend → FastAPI → Postgres. Covers role-differentiated journeys per PRD §3 user stories. Runs on Chrome, Edge, Firefox per NFR-COMPAT-001. SSO is stubbed via a test IdP. | Playwright | 5–15 min | Pre-merge to main + nightly |

**Tier selection rule:** if a behavior can be tested at B1 it must be tested at B1 — don't push pure-logic tests into B2/B3 just because the module is wired through the DB. Validators (`BudgetUploadValidator`, etc.) are **B1**, even though their callers are B2/B3.

**E2E coverage scope** (intentionally narrow — Playwright is expensive):
1. Filing-unit manager: SSO login → download template → upload valid Excel → see version → upload invalid Excel → see row-level errors
2. HR admin: SSO login → upload valid CSV → see notification confirmation → upload invalid CSV → see row errors
3. Finance admin: open cycle → see all units in dashboard → trigger resubmit → see flag
4. Reviewer at 1000處: see consolidated report with 3 columns + actuals
5. 0000公司 reviewer: log in → see only consolidated report (no upload UI surfaces)
6. IT auditor: query audit log + verify chain

### Fixture Strategy

#### Backend `tests/fixtures/`

| Fixture set | Purpose | Used by |
|-------------|---------|---------|
| `excel/budget_valid.xlsx` | Valid template with prefilled actuals + filled budgets | B2, B3 |
| `excel/budget_dept_mismatch.xlsx` | Wrong dept code in cell | B2 (`UPLOAD_003`) |
| `excel/budget_negative_amount.xlsx` | Row with negative amount | B2 (`UPLOAD_006`) |
| `excel/budget_oversize.xlsx` | > 5000 rows | B2 (`UPLOAD_002`) |
| `excel/budget_too_big.bin` | > 10 MB binary | B2 (`UPLOAD_001`) |
| `csv/personnel_valid.csv` | Valid HR import | B2, B3 |
| `csv/personnel_bad_dept.csv` | dept_id not in tree | B2 (`PERS_001`) |
| `csv/personnel_wrong_category.csv` | account is operational, not personnel | B2 (`PERS_002`) |
| `csv/personnel_negative.csv` | Negative amount | B2 (`PERS_003`) |
| `csv/shared_cost_valid.csv` + 3 invalid variants | Mirror of personnel set for `SHARED_*` codes | B2 |
| `seed/org_tree_small.sql` | 12-unit org tree spanning 0000→0500→1000→2000→4000 levels | B2, B3 |
| `seed/org_tree_large.sql` | 150-unit org tree for B4 perf | B4 |
| `seed/account_master.sql` | ~80 accounts across operational/personnel/shared_cost categories | B2, B3, B4 |
| `seed/users.sql` | One user per role (FinanceAdmin, HRAdmin, FilingUnitMgr ×3, Reviewer ×2, 0000Reviewer, ITAuditor, SystemAdmin) | All tiers |
| `expected/consolidated_report_small.json` | Golden output for the small fixture set | B3, B4 |

#### `conftest.py` shared fixtures (backend)
- `db_session` — clean Postgres session per test (testcontainers, transaction-rollback strategy)
- `app_client` — `httpx.AsyncClient` with FastAPI app + dependency overrides
- `seeded_db` — applies `seed/*` SQL fixtures
- `frozen_clock` — overrides `core/clock.now_utc` to a deterministic value
- `fake_smtp` — captures sent messages instead of sending
- `fake_sso` — issues a deterministic JWT for any user fixture
- `tmp_storage` — overrides `infra/storage` root to a `tmp_path`

#### Frontend `tests/fixtures/`
- `api/*.json` — recorded API responses for msw mocks (one file per endpoint)
- `e2e/seed.sql` — same shape as backend small seed; loaded into the E2E DB before each suite
- `e2e/test-idp/` — minimal OIDC IdP stub (Authlib `AuthorizationServer`) seeded with the same users

#### Golden file policy
- Golden files at `backend/tests/fixtures/expected/` are **append-only**: new scenarios add new files; existing files are only updated when an FR formally changes (with the change recorded in the test commit message).
- Generated XLSX templates have a separate golden suite (`expected/templates/{org_unit_code}.xlsx`) — comparison is sheet-by-sheet, cell-by-cell, ignoring file metadata fields (creation timestamp).

### High-Risk Test Areas

| Module | Risk type | Minimum test cases |
|--------|-----------|-------------------|
| **M9 `audit`** | **Silent corruption** — broken hash chain that nothing notices until an audit query, by which time the chain may have advanced past recovery | (1) record N entries, verify chain length N; (2) record + tamper one row → `verify_chain` returns `AUDIT_001`; (3) concurrent record from two tasks must produce a valid chain (sequencing test); (4) record then DB rollback → no orphan chain row; (5) verify_chain on empty range; (6) verify_chain across 10k rows in B4 perf |
| **M10 `core/security` (RBAC)** | **Silent over-permission** — false approvals leak data invisibly | Per role × per resource type matrix: (1) FilingUnitMgr scoped to unit X → 200 on own unit, 403 on sibling unit; (2) Reviewer at 1000處 → see all subtree, 403 on sibling 1000處; (3) 0000公司 Reviewer → 200 on consolidated report, 403 on `/dashboard` upload list, 403 on uploads; (4) HRAdmin → 200 on personnel-budgets, 403 on budget-uploads; (5) ITAuditor → 200 on audit-logs, 403 on every other resource; (6) URL-direct access bypassing UI must still 403; (7) RBAC denial must record an audit log entry |
| **M4 `budget_uploads`** | **Silent failure** in collect-then-report — missed row error means a partial-write into DB | (1) Each row error code (UPLOAD_003..006) emits exactly the expected `details` row; (2) any row error → zero `BudgetLine` rows persisted (integral commit, verified by counting rows); (3) duplicate dept_code in same upload; (4) account code in wrong category (operational vs personnel); (5) amount with thousands separator / scientific notation; (6) Excel formula cells; (7) Unicode dept names; (8) merged cells (must be flat); (9) version increments correctly under concurrent uploads (DB unique constraint test); (10) file_hash recorded matches sha256 of bytes |
| **M5 `personnel`** + **M6 `shared_costs`** | Same collect-then-report risks as M4, plus CSV encoding | Same matrix as M4 adapted to PERS_*/SHARED_* codes; **plus** (a) UTF-8 BOM; (b) Big5 encoding rejection with clear error; (c) CRLF vs LF; (d) trailing empty rows; (e) commas inside quoted fields |
| **M7 `consolidation`** | **Precision** in delta-pct, **scope leakage** when joining 3 sources, **performance** at NFR-PERF-002 | (1) Three-source join with sparse data (some org units have only operational, no personnel); (2) Personnel + shared_cost columns are `null` for org units below 1000處 (per FR-015); (3) `delta_pct` = "N/A" when actual = 0 (FR-016); (4) `budget_status` = "not_uploaded" when no upload exists; (5) report respects `RBAC.scoped_org_units(user)` — Reviewer at 1000處 cannot see other 1000處 subtrees; (6) **B4 perf:** 100-unit consolidated report < 15s on dev hardware; (7) async export: enqueue → status transitions → file downloadable → Email sent; (8) golden-file regression on small fixture |
| **M1 `cycles`** | State machine + 5 FRs: invalid transitions could leave the system in an inconsistent state | (1) Each illegal transition (`Open→Open`, `Closed→Open` outside reopen window, `Closed→Closed`) raises the right code; (2) `assert_open` raises CYCLE_004 on Closed; (3) `list_filing_units` excludes 6000/5000/0000; (4) `CYCLE_002` blocks `open` if any filing unit lacks a manager; (5) reopen within window OK, after window CYCLE_005; (6) reminder schedule persists & is serializable; (7) `dispatch_deadline_reminders` skips already-uploaded units; (8) dispatcher runs without crashing on zero open cycles |
| **M3 `templates`** | Generation correctness — wrong actuals in the wrong template = wrong budgets uploaded later | (1) Filing unit with zero actuals → template still produced, actuals column = 0 (FR-009 boundary); (2) Personnel + shared_cost accounts excluded from template; (3) Generated workbook round-trips through `BudgetUploadValidator` cleanly (no validator-vs-generator drift); (4) `regenerate` overwrites previous file atomically (no half-written file on failure); (5) Download authorization: only the unit's manager + scoped reviewers + FinanceAdmin can download; (6) Download is audit-logged |
| **M11 `api/v1` open-cycle pipeline** | Multi-step orchestration where partial failure must not corrupt state | (1) cycles.open commits, templates.generate fails for 2 units → cycle stays Open, dashboard shows 2 retry-needed; (2) cycles.open commits, all templates ok, notifications.send_batch SMTP fails → cycle Open, templates exist, notification batch flagged failed but resendable; (3) RBAC failure at step 1 → no state change; (4) double-open on already-Open cycle → CYCLE_003, no side effects |

---

## 9. Implementation Order

### Batch Sequence

Topologically sorted from the §4 import graph. Modules in the same batch have **no inter-dependencies within the batch** and can be built in parallel by independent agents/developers.

| Batch | Modules | Depends on | Parallelizable | Notes |
|-------|---------|------------|----------------|-------|
| **0** — Foundation | `core/clock`, `core/errors`, `core/logging`, `infra/db` (session + base ORM), `infra/crypto`, `infra/storage`, `infra/excel`, `infra/csv_io`, `infra/email` (with fake_smtp test double), `infra/sso` (with fake_sso test double), `infra/scheduler`, `infra/jobs` (table + worker shell, no handlers yet), Alembic baseline migration, FastAPI app skeleton + global error handler | — | ✅ Yes | All infra adapters built against unit tests with stubs/fakes. No domain logic yet. **Spike checks:** docker-compose up brings up Postgres + backend skeleton; OIDC stub IdP issues a token end-to-end. |
| **1** — Audit | `domain/audit` (AuditService, hash chain, ORM model, migration) | Batch 0 | n/a | **Critical path.** Hash chain must be correct before any other domain module wires audit calls. Includes B1 + B2 hash-chain tests. |
| **2** — Security | `core/security` (M10): SSO callback, JWT mint/verify, session cookies + CSRF, RBAC dependencies, User + Role ORM models | Batches 0-1 | n/a | Once green, every subsequent module wires `RBAC.require_*` dependencies into its routes. |
| **3** — Notifications | `domain/notifications` (M8): NotificationService, ResubmitRequest store, ORM + migration. Email templates rendered against fake_smtp. | Batches 0-2 | n/a | Built before `cycles` because `cycles` will call `send_batch`. |
| **4** — Accounts | `domain/accounts` (M2): AccountCode + ActualExpense ORM, master CRUD, actuals bulk import (`POST /cycles/{id}/actuals/import`) | Batches 0-2 | ✅ may run in parallel with Batch 3 (different teams) | |
| **5** — Cycles | `domain/cycles` (M1): cycle state machine, filing-unit query, reminder schedule, deadline-reminder dispatcher (registers cron at app startup) | Batches 0-3 | n/a | **Bottleneck — 5 FRs and a state machine.** Includes the cron-callback registration but the dispatcher relies on a shared `infra/db.repos.budget_uploads.unsubmitted_for_cycle` query which must be added in Batch 6 — until then dispatcher logs a stub. |
| **6** — Upload modules | `domain/budget_uploads` (M4), `domain/personnel` (M5), `domain/shared_costs` (M6), `domain/templates` (M3) | Batches 0-5 | ✅ All four can be built in parallel — they share no code with each other, only share dependencies on cycles + accounts + notifications | M4/M5/M6 are nearly identical in structure (validator + version snapshot + notify); they should be built **in parallel by separate agents** following a common pattern. M3 is independent of M4/M5/M6. |
| **7** — Consolidation | `domain/consolidation` (M7): dashboard query, three-source consolidated report, async export job + handler, registered with `infra/jobs` | Batches 0-6 | n/a | Largest read-side module. Includes B4 perf tests against the large seed. |
| **8** — API surface | `api/v1` route handlers (M11) for any endpoints not already added incrementally in Batches 4-7 + the open-cycle orchestration pipeline + Pydantic request/response schemas + OpenAPI polish | Batches 0-7 | ✅ Routes can be parallelized by resource group | Most domain modules will have stub routes added in their own batches; this batch consolidates, fills gaps, and adds the pipeline orchestrator. |
| **9** — Frontend foundation | Vite + React Router skeleton, Mantine theme (PRD §8.1 design tokens), i18n (zh-TW), TanStack Query setup, axios with cookie auth + CSRF interceptor, `/auth/me` flow, role-derived navigation guards | Batches 0-2 (backend SSO endpoints) | ✅ may run in parallel with Batches 3-8 once backend SSO is green | Frontend can begin in parallel with backend Batch 3+ once `/api/v1/auth/me` works against the SSO stub. |
| **10** — Frontend feature pages | All 11 pages from §5 frontend table | Batch 9 + corresponding backend batch | ✅ One page per backend feature can run in parallel | Each page depends on a specific backend batch — e.g. Upload page needs Batch 6, Dashboard/Reports need Batch 7. |
| **11** — E2E + perf hardening | Playwright suites, B4 backend perf, golden-file generation, accessibility audit (NFR-ACC-001) | Batches 0-10 | ✅ E2E scenarios independent | Final pre-release tier. |

### Critical Path

```
Batch 0  →  Batch 1 (audit)  →  Batch 2 (security)  →  Batch 3 (notifications)  →  Batch 5 (cycles)  →  Batch 6 (uploads)  →  Batch 7 (consolidation)  →  Batch 8 (api)  →  Batch 11 (e2e)
```

The longest sequential chain is **9 batches** (Batch 4 `accounts` runs in parallel with Batch 3 `notifications`, and the frontend tracks runs in parallel with Batches 3-10). The critical path is gated by **`cycles` (Batch 5)** because four of the upload modules wait on it; getting `cycles` right and merged is the highest-leverage milestone.

### Bottleneck Modules

| Module | Why it's a bottleneck | Mitigation |
|--------|----------------------|------------|
| **M1 `cycles`** | 5 FRs, state machine, dispatcher cron, blocks Batch 6 (4 modules) | Treat as a single dedicated workstream; do not split across agents. Apply size-warning split plan from §4 if it grows beyond 500 lines. |
| **M9 `audit`** | Single point of correctness for FR-023; every other module records to it; bug here corrupts the chain irrecoverably | Build first (Batch 1). Hash-chain unit + concurrency tests are blocking before Batch 2 starts. |
| **M7 `consolidation`** | 4 FRs, three-source join, perf-sensitive, async export | Allocate B4 perf budget early (in Batch 7), not as a Batch 11 retrofit. |
| **M10 `core/security`** | RBAC matrix is silent-failure-prone; blocks every authenticated route | Test matrix in Batch 2 must enumerate every (role × resource) pair before declaring done. |

### Early Validation Spikes (Batch 0)

These must pass before any domain code is written — they validate the foundation:

1. **Container spike:** `docker-compose up` brings backend (FastAPI), Postgres 16, Nginx, fake-SMTP, fake-IdP — all healthy, all reachable, TLS termination working. 30 minutes max if it takes longer the toolchain is wrong.
2. **SSO round-trip:** Hit `/api/v1/auth/sso/login` against the stub IdP, complete callback, receive `bc_session` cookie, call `/api/v1/auth/me` and get a user back. No domain modules involved.
3. **Hash-chain primitive:** `infra/crypto.chain_hash(prev, payload)` produces a deterministic, tamper-evident chain across 1000 entries in < 1s. Establishes the algorithm before `domain/audit` consumes it.
4. **AES-GCM round-trip:** `infra/crypto.encrypt_field` / `decrypt_field` round-trips a 1KB payload with key from env var. Validates the **non-pgcrypto** decision before any column-encrypted ORM models exist.
5. **Excel round-trip:** `infra/excel.write_workbook(...)` followed by `read_workbook(...)` preserves cell types (numeric, text, formula). Uses one of the validator-vs-generator pairs to confirm openpyxl behavior matches expectations.
6. **Job runner spike:** Enqueue a no-op job, worker picks it up, marks succeeded, status queryable. Validates the durable-job design before `consolidation` depends on it.

---

## 9. Implementation Order

### Batch Sequence

| Batch | Modules | Depends On | Parallelizable |
|-------|---------|------------|----------------|
| | | | |
