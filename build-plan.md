# BCMS Build Plan

## PRD Format Analysis

PRD v4.3 functional requirements live in **§4 Functional Requirements**, grouped into 8 capability subsections (§4.1 Budget Cycle Management, §4.2 Excel Template, §4.3 Budget Upload, §4.4 HR Personnel Budget Import, §4.5 Shared Cost Import, §4.6 Dashboard & Consolidated Reports, §4.7 Notification & Resubmission, §4.8 Account & Security). FR ID scheme is `FR-NNN` (zero-padded 3-digit, FR-001 .. FR-029, with FR-024..FR-029 added in v4.2). FR rows use a 4-column table format: **FR ID | 功能 (function) | 說明 (prose covering Input / Rules / Output / Error / boundary conditions / 邊界條件 / 錯誤處理 / 刷新頻率) | 優先級 (P0/P1)**. Inputs/outputs/error handling are not separate fields — they are embedded in the 說明 prose, often in bold sub-labels. There is no explicit `Depends` field; dependencies are inferred from §10 Data Entities and §6 Workflow. Optional sections present and used: §1 Overview, §2.4 In-Scope Capabilities, §3 User Stories with FR mapping, §5 Roles & Permissions, §6 Workflow, §7 Security, §8 Design Specs, §9 NFRs (NFR-PERF/REL/SEC/COMPAT/USE/ACC), §10 Data Entities (15 entities), §11 Milestones (Phase 1/2/3), §12 Success Metrics, §13 Risk Register, §14 Technology Constraints (Decided / Open).

## 1. Build Config

| Key | Value |
|---|---|
| `language` | Python 3.12 (PRD/Architecture locked; ≥3.11 acceptable per global convention) |
| `package_manager` | `uv` (architecture §1, "uv 0.5.x"); fallback `pip + venv` if uv unavailable |
| `test_command` | `uv run pytest backend/tests/ --tb=short` |
| `lint_command` | `uv run ruff check backend/src/` |
| `lint_tool` | `ruff` (replaces black/flake8/isort per architecture §1) |
| `type_check_command` | `uv run pyright backend/src/` |
| `type_check_tool` | `pyright` (architecture §1; mypy is the global default but architecture explicitly locks pyright — pyright wins) |
| `format_command` | `uv run ruff format backend/src/` |
| `format_tool` | `ruff format` (architecture §1 — ruff is both linter and formatter; black not used) |
| `run_command` | `uv run uvicorn app.main:app --reload` (dev); worker: `uv run python -m app.infra.jobs.worker` |
| `src_dir` | `backend/src/app/` |
| `test_dir` | `backend/tests/` |
| `stub_detection_pattern` | `NotImplementedError\|TODO:\|FIXME:\|^\s*pass\s*$\|^\s*\.\.\.\s*$\|raise\s+NotImplementedError` |
| `migration_command` | `uv run alembic upgrade head` |
| `db_revision_command` | `uv run alembic revision --autogenerate -m "<msg>"` |

## 2. Gate Configuration

| Gate | Enabled | Command |
|---|---|---|
| `lint` | yes | `uv run ruff check backend/src/` |
| `format_check` | yes | `uv run ruff format --check backend/src/` |
| `type_check` | yes | `uv run pyright backend/src/` |
| `unit_tests` | yes | `uv run pytest backend/tests/unit -q` |
| `integration_tests` | yes (Postgres required) | `uv run pytest backend/tests/integration -q` |
| `api_tests` | yes | `uv run pytest backend/tests/api -q` |
| `migration_check` | yes | `uv run alembic upgrade head && uv run alembic check` |
| `stub_scan` | yes | grep against `stub_detection_pattern` over `backend/src/app/` |
| `frontend_lint` | deferred to frontend phase | `pnpm lint` (in `frontend/`) |
| `frontend_type_check` | deferred | `pnpm exec tsc --noEmit` |
| `frontend_test` | deferred | `pnpm test` |
| `e2e` | deferred to Batch 11 | `pnpm exec playwright test` |

Frontend gates are disabled at the start of build; they activate when Batch 9 begins.

## 3. Project Summary

- **Project root:** `C:/Users/Liou/Projects/BCMS`
- **Type:** Greenfield monorepo. Only `docs/`, `.gitignore`, `.claude/` exist on disk today. No `pyproject.toml`, no `src/`, no `tests/`, no lockfile yet.
- **Layout (per architecture §2):** `backend/` + `frontend/` + `deploy/` + `docs/`. This plan covers the **backend** completely and reserves the **frontend** as Batches 9–10 (informational batches; subagents may build the React app once backend SSO + at least one feature endpoint is green).
- **Backend stack:** Python 3.12, FastAPI 0.115.x, SQLAlchemy 2.0 async + asyncpg, Pydantic 2.9.x, Alembic, Authlib (OIDC/SAML), PyJWT, openpyxl, aiosmtplib, APScheduler (cron only), structlog, cryptography (AES-256-GCM + HMAC hash chain), pytest + pytest-asyncio + httpx, ruff, pyright, uv. PostgreSQL 16 backend.
- **Frontend stack (informational, build deferred):** TypeScript 5.6 + React 18.3 + Vite + React Router + TanStack Query + Mantine 7 + react-hook-form + zod + axios + react-i18next + Vitest + Playwright; pnpm.
- **Deployment target:** Single-host intranet, docker-compose, Nginx TLS termination, local encrypted volume for file storage. No cloud KMS, no S3.
- **Greenfield note:** No existing source to map. All paths under `backend/src/app/` and `backend/tests/` will be created by Batch 0. All conventions are captured in `build-context.md`.

## 4. FR → Subsystem Map

| FR | Subsystem (Module) | Acceptance criterion (verbatim or condensed from PRD §4 / §3) |
|---|---|---|
| FR-001 | M1 `domain/cycles` | Create draft cycle with fiscal_year/deadline/reporting_currency; only one non-closed cycle per fiscal_year (UNIQUE INDEX); raises `CYCLE_001` on conflict. |
| FR-002 | M1 `domain/cycles` (+ admin endpoints) | List filing units (4000–0500 inclusive) for the cycle; surface `has_manager` flag; if any filing unit lacks a manager, block cycle open with `CYCLE_002` until corrected or explicitly excluded. 6000/5000/0000 are NOT filing units. |
| FR-003 | M1 `domain/cycles` | State transition Draft → Open only (raises `CYCLE_003` otherwise); on success triggers template generation for every filing unit (excluding 0000) and dispatches `cycle_opened` notification batch; bounce flagged on dashboard, resendable. |
| FR-004 | M7 `domain/consolidation` (DashboardService) | Per-role-scoped dashboard returns each filing unit's status (`not_downloaded` / `downloaded` / `uploaded` / `resubmit_requested`) within ≤5s of the state change. Empty cycle returns "尚未開放週期" sentinel. |
| FR-005 | M1 `domain/cycles` (reminders) + M8 `domain/notifications` | Reminder schedule `days_before` (e.g. 7/3/1) persisted; APScheduler cron at 09:00 server TZ scans Open cycles, calls dispatcher; already-uploaded units excluded. |
| FR-006 | M1 `domain/cycles` | Open → Closed (manual or deadline-triggered); after Closed all writes (budget, personnel, shared cost) raise `CYCLE_004`. Reopen permitted within `BC_REOPEN_WINDOW_DAYS` window with reason; SystemAdmin only; raises `CYCLE_005` after window. |
| FR-007 | M2 `domain/accounts` | Account master CRUD with `category ∈ {operational, personnel, shared_cost}` and `level`; codes referenced by category by importers. |
| FR-008 | M2 `domain/accounts` | Bulk actuals import (CSV/Excel) per cycle; collect-then-report row validation; on any failure raises `ACCOUNT_002` with row-level details and persists nothing (integral commit). |
| FR-009 | M3 `domain/templates` | For each filing unit (4000–0500, excluding 0000), generate Excel template prefilling dept code + name + per-account actuals (operational accounts only — NO personnel, NO shared_cost columns); zero actuals → display 0; per-unit failures recorded as `generation_error` and surfaced for retry, not aborted globally. |
| FR-010 | M3 `domain/templates` | Authorized download; only for the requesting user's scoped org unit; raises `TPL_002` if not yet generated, `RBAC_002` if wrong unit. Increments `download_count`. |
| FR-011 | M4 `domain/budget_uploads` | Upload `.xlsx` (≤10 MB → `UPLOAD_001`; ≤5000 rows → `UPLOAD_002`); validates dept code matches assigned org unit (`UPLOAD_003`), required cells non-empty (`UPLOAD_004`), amount format (`UPLOAD_005`), amount ≥ 0 (`UPLOAD_006`); collect-then-report; on any failure raises `UPLOAD_007` with row-level details and zero rows persisted. |
| FR-012 | M4 `domain/budget_uploads` | Each successful upload creates a new monotonic `version` per `(cycle_id, org_unit_id)` with uploader, timestamp, file hash. Latest version is the effective version. History read-only, retained ≥5 years past cycle close. |
| FR-013 | M4 `domain/budget_uploads` + M8 `domain/notifications` | On successful upload, send `upload_confirmed` email to uploader and direct upline manager including version + filename. Notification failure does not invalidate the upload but is logged in audit and flagged for resend. |
| FR-014 | M7 `domain/consolidation` (DashboardService) | Role-scoped dashboard with filter + sort + pagination; shows last upload time + version; ≤5s reflection; falls back to last snapshot with `stale: true` on backend issue. 0000公司 Reviewer dashboard is summary-only (no items). |
| FR-015 | M7 `domain/consolidation` (ConsolidatedReportService) | Per-scope report joining latest budget_uploads + personnel_uploads + shared_cost_uploads by `(org_unit, account_code)`; for org units at level 1000處 or higher, the personnel_budget and shared_cost columns are populated; report returns three "last_updated_at" timestamps (one per source). |
| FR-016 | M7 `domain/consolidation` | Per-row `actual` and `delta_amount`/`delta_pct` (1 decimal) computed; `delta_pct = "N/A"` when actual is 0; `budget_status = "not_uploaded"` when no upload yet. |
| FR-017 | M7 `domain/consolidation` + `infra/jobs` | Export request returns 201 (sync) for ≤`BC_ASYNC_EXPORT_THRESHOLD` units, otherwise 202 + `job_id` enqueued to durable runner; on completion sends email to requester; failure raises `REPORT_002`. |
| FR-018 | M8 `domain/notifications` (ResubmitRequestService) | FinanceAdmin or upline reviewer creates a resubmit request with reason; emails the unit's manager with reason + template download link; dashboard flags `resubmit_requested`. |
| FR-019 | M8 `domain/notifications` | Resubmit request persisted with requester/timestamp/reason/target_unit/target_version; record write failure raises `NOTIFY_002` AND blocks email send (no "sent without record" state). |
| FR-020 | M1 `domain/cycles` dispatcher + M8 `domain/notifications` | The same daily 09:00 cron invokes deadline-reminder dispatch; recipients are filing-unit managers cc'd to direct upline reviewers. |
| FR-021 | M10 `core/security` + `infra/sso` | Authlib OIDC/SAML callback → role mapping from IdP groups via `BC_SSO_ROLE_MAPPING`; sets `bc_session` + `bc_refresh` + `bc_csrf` HttpOnly cookies; mapping failure raises `AUTH_003`; IdP unreachable raises `AUTH_001`. Local accounts forbidden. |
| FR-022 | M10 `core/security` (RBAC) | Per-role + per-org-unit scope check enforced as FastAPI dependency on every protected route; raises `RBAC_001`/`RBAC_002` (403) and writes audit entry; URL direct access blocked server-side. 0000公司 Reviewer sees only consolidated report; HRAdmin sees only personnel import; etc. |
| FR-023 | M9 `domain/audit` | Append-only `audit_logs` table with `sequence_no` BIGSERIAL + HMAC `prev_hash`/`hash_chain_value`; UPDATE/DELETE revoked at DB level; `verify_chain(start, end)` re-hashes the range and raises `AUDIT_001` on mismatch. ≥5 year retention. Filterable query interface. |
| FR-024 | M5 `domain/personnel` | HR uploads CSV/Excel `(dept_id, account_code, amount)`; validates dept_id in org tree (`PERS_001`), account_code is personnel category (`PERS_002`), amount > 0 (`PERS_003`); collect-then-report → `PERS_004` on any row failure with integral commit semantics. |
| FR-025 | M5 `domain/personnel` | Per-cycle versioning; later upload supersedes earlier; each upload snapshot stores `(uploader, timestamp, affected_org_units_summary)`; history read-only; upload event written to audit log. |
| FR-026 | M5 `domain/personnel` + M8 `domain/notifications` | On successful import, notify FinanceAdmin via email; consolidated report immediately reflects new version. |
| FR-027 | M6 `domain/shared_costs` | Finance uploads CSV/Excel `(dept_id, account_code, amount)`; validates dept_id (`SHARED_001`), shared_cost-category code (`SHARED_002`), amount > 0 (`SHARED_003`); collect-then-report → `SHARED_004`. |
| FR-028 | M6 `domain/shared_costs` | Per-cycle versioning identical in shape to FR-025, plus per-org-unit amount diff summary in `affected_org_units_summary`. |
| FR-029 | M6 `domain/shared_costs` + M8 `domain/notifications` | On successful import, compute `diff_affected_units(prev, new)` and email each affected department's manager; consolidated report updates immediately. |

## 5. Shared Utilities

These live outside any single FR-owning module and are imported by 2+ modules. They MUST be implemented in Batch 0 or Batch 6 (depending on whether infra or domain).

### 5.1 `core/clock.now_utc`
- **Signature:** `def now_utc() -> datetime`
- **Placement:** `backend/src/app/core/clock.py`
- **Consumers:** every domain module (M1 cycles, M4–M6 importers, M7 consolidation, M8 notifications, M9 audit, M10 security, all `infra/jobs` callbacks)
- **Note:** Single seam for testability — fixtures patch `app.core.clock.now_utc`. Returns timezone-aware UTC `datetime`. No `datetime.now()` is permitted anywhere else in `src/`.

### 5.2 `core/errors.AppError` + registry
- **Signatures:**
  - `class AppError(Exception): def __init__(self, code: str, message: str, *, http_status: int, details: list[dict] | None = None) -> None`
  - Subclasses: `BatchValidationError(AppError)`, `NotFoundError(AppError)`, `ConflictError(AppError)`, `ForbiddenError(AppError)`, `UnauthenticatedError(AppError)`, `InfraError(AppError)`
  - `ERROR_REGISTRY: dict[str, tuple[int, str]]` mapping every code from architecture §3 (AUTH_001..AUDIT_002 + SYS_001..SYS_003) to `(http_status, default_message_template)`.
- **Placement:** `backend/src/app/core/errors.py`
- **Consumers:** every module + the global FastAPI exception handler in `app/main.py`.
- **Note:** Each error code is defined in EXACTLY ONE place (the registry). Subclasses pick `code` from the registry; HTTP status comes from the registry. Global exception handler emits the envelope from architecture §3.

### 5.3 `domain/_shared/row_validation`
- **Signatures:**
  - `@dataclass class RowError: row: int; column: str | None; code: str; reason: str; def to_dict(self) -> dict`
  - `@dataclass class ValidationResult: rows: list[dict]; errors: list[RowError]; @property def valid(self) -> bool`
  - `def clean_cell(value: object | None) -> str | None`
  - `def parse_amount(value: object | None, *, allow_zero: bool) -> Decimal` raises `AmountParseError` (not `AppError`)
  - `class AmountParseError(ValueError)`
- **Placement:** `backend/src/app/domain/_shared/row_validation.py`
- **Consumers:** M2 `accounts` (actuals import), M4 `budget_uploads`, M5 `personnel`, M6 `shared_costs`. Owned by NO domain module — `_shared` is the canonical home.
- **Note:** `clean_cell` strips whitespace, treats empty string and `None` identically. `parse_amount` accepts `int | float | str | Decimal | None`, normalizes to `Decimal(...).quantize(Decimal("0.01"))`, raises on non-numeric, raises on negative, and on zero only when `allow_zero=False` (FR-024/027 personnel/shared_cost require positive; FR-011 budget allows zero).

### 5.4 `domain/_shared/queries.org_unit_code_to_id_map`
- **Signature:** `async def org_unit_code_to_id_map(db: AsyncSession) -> dict[str, UUID]`
- **Placement:** `backend/src/app/domain/_shared/queries.py`
- **Consumers:** M5 `personnel`, M6 `shared_costs`, M2 `accounts` actuals importer.
- **Note:** Single SELECT used by every importer to translate the user-supplied `dept_id` column into an internal `org_unit_id`. Cached per-request via FastAPI dep, NOT module-global, to remain testable.

### 5.5 `infra/db.helpers.next_version`
- **Signature:** `async def next_version(db: AsyncSession, model: type, **filters: object) -> int`
- **Placement:** `backend/src/app/infra/db/helpers.py`
- **Consumers:** M4 `budget_uploads`, M5 `personnel`, M6 `shared_costs`.
- **Note:** Returns `MAX(version) + 1 OR 1` over the filtered subset. Must be called inside the same transaction that inserts the new row to be race-safe (rely on row-level locking or the table's UNIQUE constraint to retry on conflict). Single canonical implementation.

### 5.6 `infra/tabular.parse_table`
- **Signature:** `async def parse_table(filename: str, content: bytes) -> list[dict[str, object]]`
- **Placement:** `backend/src/app/infra/tabular.py`
- **Consumers:** M2 actuals importer, M5 personnel, M6 shared_costs.
- **Note:** Single dispatcher: `.csv` → `infra/csv_io.parse_dicts`; `.xlsx` → `infra/excel.read_rows`. Domain code MUST NOT re-implement the extension dispatch. Returns each row as a `dict[str, object]` with header keys preserved.

### 5.7 `infra/crypto` primitives
- **Signatures:**
  - `def encrypt_field(plaintext: bytes, *, key_id: str | None = None) -> bytes`
  - `def decrypt_field(ciphertext: bytes) -> bytes`
  - `def hmac_lookup_hash(value: bytes) -> bytes`  (deterministic, for `users.email_hash` / `users.sso_id_hash`)
  - `def chain_hash(prev_hash: bytes, payload: bytes) -> bytes`  (HMAC-SHA256 with `BC_AUDIT_HMAC_KEY`)
- **Placement:** `backend/src/app/infra/crypto/`
- **Consumers:** M9 audit (chain_hash), M10 security (HMAC lookup + AES for refresh hash), `infra/db` ORM models for any encrypted column.
- **Note:** AES-256-GCM. Each ciphertext carries a 12-byte nonce + 16-byte tag prefix. Key loaded from `BC_CRYPTO_KEY`. NEVER use `pgcrypto` for symmetric encryption.

### 5.8 `infra/storage` async file I/O
- **Signature:**
  - `async def save(category: str, filename: str, content: bytes) -> str` (returns opaque storage key)
  - `async def read(storage_key: str) -> bytes`
  - `async def delete(storage_key: str) -> None`
- **Placement:** `backend/src/app/infra/storage/`
- **Consumers:** M3 templates, M4–M6 importers, M7 export job handler.
- **Note:** Wraps blocking `open()` in `run_in_threadpool` so the event loop never stalls. Domain modules NEVER call `open()` directly. Path construction is owned here.

### 5.9 `core/security.RBAC` dependencies
- **Signatures:**
  - `def require_role(*roles: Role) -> Callable[[User], User]`  (FastAPI Depends factory)
  - `def require_scope(resource_type: str, resource_id_param: str) -> Callable[..., None]`
  - `async def scoped_org_units(user: User, db: AsyncSession) -> set[UUID]`
- **Placement:** `backend/src/app/core/security/rbac.py`
- **Consumers:** every `api/v1` route handler.
- **Note:** Single source of role-vs-resource truth. Failures raise `RBAC_001` / `RBAC_002`, which the global exception handler maps to 403 + audit log entry.

## 6. Batch Plan

12 modules total (M1–M11 + frontend track). Target ≤ ⌈12/6⌉ = **2-batch minimum**, but the dependency graph in architecture §4 forces a longer chain. The plan below follows the architecture's §9 sequence with single-module batches merged forward where compatible. Batches 9–10 (frontend) are deferred and can run in parallel with the backend tail.

### Batch 0 — Foundation (infra adapters + Pydantic settings + Alembic baseline)

| Item | Path | Test path | Complexity |
|---|---|---|---|
| Project skeleton + uv `pyproject.toml` + lockfile | `backend/pyproject.toml`, `backend/uv.lock` | n/a | simple |
| `app/main.py` FastAPI app + global exception handler + request_id middleware | `backend/src/app/main.py` | `backend/tests/api/test_main.py` | moderate |
| `app/config.py` Pydantic Settings (every `BC_*` env var from architecture §7) | `backend/src/app/config.py` | `backend/tests/unit/test_config.py` | simple |
| `app/core/clock.py` (§5.1) | `backend/src/app/core/clock.py` | `backend/tests/unit/core/test_clock.py` | simple |
| `app/core/errors.py` AppError + registry (§5.2) | `backend/src/app/core/errors.py` | `backend/tests/unit/core/test_errors.py` | moderate |
| `app/core/logging.py` structlog config | `backend/src/app/core/logging.py` | `backend/tests/unit/core/test_logging.py` | simple |
| `app/infra/db/session.py` async engine + AsyncSession factory | `backend/src/app/infra/db/session.py` | `backend/tests/integration/infra/test_db_session.py` | simple |
| `app/infra/db/base.py` DeclarativeBase | `backend/src/app/infra/db/base.py` | n/a | simple |
| `app/infra/db/helpers.py` (§5.5) | `backend/src/app/infra/db/helpers.py` | `backend/tests/integration/infra/test_db_helpers.py` | simple |
| `app/infra/crypto/` encrypt/decrypt/hmac/chain (§5.7) | `backend/src/app/infra/crypto/__init__.py` | `backend/tests/unit/infra/test_crypto.py` | moderate |
| `app/infra/storage/` async save/read/delete (§5.8) | `backend/src/app/infra/storage/__init__.py` | `backend/tests/unit/infra/test_storage.py` | moderate |
| `app/infra/excel/` openpyxl helpers (`open_workbook`, `read_rows`, `write_workbook`, `workbook_to_bytes`) | `backend/src/app/infra/excel/__init__.py` | `backend/tests/unit/infra/test_excel.py` | moderate |
| `app/infra/csv_io/` `parse_dicts(bytes) -> list[dict]` UTF-8 only | `backend/src/app/infra/csv_io/__init__.py` | `backend/tests/unit/infra/test_csv_io.py` | simple |
| `app/infra/tabular.py` (§5.6) | `backend/src/app/infra/tabular.py` | `backend/tests/unit/infra/test_tabular.py` | simple |
| `app/infra/email/` aiosmtplib client + Jinja template renderer + `fake_smtp` test double | `backend/src/app/infra/email/__init__.py` | `backend/tests/unit/infra/test_email.py` | moderate |
| `app/infra/sso/` Authlib OIDC/SAML wrapper + `fake_sso` test double | `backend/src/app/infra/sso/__init__.py` | `backend/tests/unit/infra/test_sso.py` | moderate |
| `app/infra/scheduler/` APScheduler wrapper (`register_cron`) | `backend/src/app/infra/scheduler/__init__.py` | `backend/tests/unit/infra/test_scheduler.py` | simple |
| `app/infra/jobs/` `enqueue`, `register_handler`, worker shell | `backend/src/app/infra/jobs/__init__.py`, `worker.py` | `backend/tests/integration/infra/test_jobs.py` | moderate |
| Alembic baseline migration covering all 18 tables (architecture §6) | `backend/alembic/versions/0001_baseline.py` | `backend/tests/integration/test_migrations.py` | complex |

**Exports table (Batch 0)**

| Symbol | Module | Signature | Purpose |
|---|---|---|---|
| `now_utc` | `core.clock` | `() -> datetime` | UTC clock seam |
| `AppError` | `core.errors` | `(code: str, message: str, *, http_status: int, details: list[dict] \| None = None)` | Base domain exception |
| `BatchValidationError` | `core.errors` | `(code: str, *, errors: list[RowError])` → AppError subclass with HTTP 400 | collect-then-report final raise |
| `NotFoundError`/`ConflictError`/`ForbiddenError`/`UnauthenticatedError`/`InfraError` | `core.errors` | `(code, message)` | typed subclasses |
| `ERROR_REGISTRY` | `core.errors` | `dict[str, tuple[int, str]]` | single source of code → status |
| `Settings` | `config` | Pydantic class with all `BC_*` fields | env-driven config |
| `get_session` | `infra.db.session` | `() -> AsyncIterator[AsyncSession]` | FastAPI dep |
| `Base` | `infra.db.base` | `DeclarativeBase` subclass | ORM base |
| `next_version` | `infra.db.helpers` | `(db, model, **filters) -> int` | shared version helper |
| `encrypt_field`/`decrypt_field`/`hmac_lookup_hash`/`chain_hash` | `infra.crypto` | see §5.7 | cryptographic primitives |
| `save`/`read`/`delete` | `infra.storage` | `async (...) -> str \| bytes \| None` | file I/O |
| `open_workbook`/`read_rows`/`write_workbook`/`workbook_to_bytes` | `infra.excel` | openpyxl helpers | xlsx I/O |
| `parse_dicts` | `infra.csv_io` | `(bytes) -> list[dict[str, str]]` | csv I/O |
| `parse_table` | `infra.tabular` | `(filename, bytes) -> list[dict[str, object]]` | dispatcher |
| `EmailClient.send` | `infra.email` | `async (template, recipient, context) -> SendResult` | SMTP egress |
| `SSOClient.exchange_code`/`fetch_userinfo` | `infra.sso` | `async (...)` | OIDC/SAML round-trip |
| `register_cron` | `infra.scheduler` | `(expr: str, callable, name: str) -> None` | cron registration |
| `enqueue`/`register_handler`/`get_status` | `infra.jobs` | see architecture §4 | durable jobs |

**Imports:** stdlib, pydantic, sqlalchemy, asyncpg, alembic, openpyxl, aiosmtplib, authlib, apscheduler, structlog, cryptography, pytest, httpx.
**Complexity:** complex (foundation breadth).

### Batch 1 — Audit (M9)

| Item | Path | Test path | Complexity |
|---|---|---|---|
| `domain/audit/service.py` AuditService.record/query/verify_chain | `backend/src/app/domain/audit/service.py` | `backend/tests/unit/audit/`, `backend/tests/integration/audit/` | complex |
| `domain/audit/models.py` SQLAlchemy AuditLog ORM | `backend/src/app/domain/audit/models.py` | n/a | simple |
| `domain/audit/repo.py` queries (filter + range) | `backend/src/app/domain/audit/repo.py` | `backend/tests/integration/audit/test_repo.py` | moderate |
| `api/v1/audit.py` GET routes | `backend/src/app/api/v1/audit.py` | `backend/tests/api/test_audit.py` | moderate |
| `domain/audit/actions.py` `AuditAction` enum (every recordable verb) | `backend/src/app/domain/audit/actions.py` | n/a | simple |

**Exports**

| Symbol | Signature |
|---|---|
| `AuditService.record` | `async (action: AuditAction, resource_type: str, resource_id: UUID \| None, user: User \| None, ip: str \| None, details: dict) -> AuditLog` |
| `AuditService.query` | `async (filters: AuditFilters) -> Page[AuditLog]` |
| `AuditService.verify_chain` | `async (start: datetime \| None, end: datetime \| None) -> ChainVerification` |
| `AuditAction` | enum: `LOGIN_SUCCESS`, `LOGOUT`, `TEMPLATE_DOWNLOAD`, `BUDGET_UPLOAD`, `PERSONNEL_IMPORT`, `SHARED_COST_IMPORT`, `NOTIFY_SENT`, `RESUBMIT_REQUEST`, `CYCLE_OPEN`, `CYCLE_CLOSE`, `RBAC_DENIED`, `AUTH_FAILED`, `LOGIN_AUTHORIZE_FAILED`, etc. |

**Imports:** `infra.db`, `infra.crypto.chain_hash`, `core.clock.now_utc`, `core.errors.AppError`.
**Complexity:** complex.

### Batch 2 — Security + Notifications (parallel pair, both lean on Batch 1)

These two have no inter-dependency (notifications doesn't call security; security only calls audit). They can run in parallel.

#### M10 `core/security`

| Item | Path | Test path | Complexity |
|---|---|---|---|
| `core/security/auth_service.py` SSO callback / refresh / logout / current_user | `backend/src/app/core/security/auth_service.py` | `backend/tests/unit/security/`, `backend/tests/integration/security/` | complex |
| `core/security/jwt.py` mint + verify HS256 | `backend/src/app/core/security/jwt.py` | `backend/tests/unit/security/test_jwt.py` | moderate |
| `core/security/sessions.py` cookie issue/refresh + Sessions ORM | `backend/src/app/core/security/sessions.py` | `backend/tests/integration/security/test_sessions.py` | moderate |
| `core/security/rbac.py` `require_role`, `require_scope`, `scoped_org_units` (§5.9) | `backend/src/app/core/security/rbac.py` | `backend/tests/unit/security/test_rbac.py` | complex |
| `core/security/csrf.py` double-submit cookie | `backend/src/app/core/security/csrf.py` | `backend/tests/unit/security/test_csrf.py` | simple |
| User + Session ORM models | `backend/src/app/core/security/models.py` | n/a | simple |
| `api/v1/auth.py` SSO routes + `/auth/me` | `backend/src/app/api/v1/auth.py` | `backend/tests/api/test_auth.py` | moderate |
| `api/v1/admin/users.py` user role mgmt | `backend/src/app/api/v1/admin/users.py` | `backend/tests/api/test_admin_users.py` | moderate |

**Exports (M10)**

| Symbol | Signature |
|---|---|
| `AuthService.handle_sso_callback` | `async (provider: str, payload: dict) -> SessionTokens` |
| `AuthService.refresh_session` | `async (refresh_token: str) -> SessionTokens` |
| `AuthService.logout` | `async (session_id: UUID) -> None` |
| `AuthService.current_user` | `async (request: Request) -> User` |
| `RBAC.require_role` | `(*roles: Role) -> Callable` |
| `RBAC.require_scope` | `(resource_type: str, resource_id_param: str) -> Callable` |
| `RBAC.scoped_org_units` | `async (user: User, db: AsyncSession) -> set[UUID]` |
| `Role` | `StrEnum` of `SystemAdmin`, `FinanceAdmin`, `HRAdmin`, `FilingUnitManager`, `UplineReviewer`, `CompanyReviewer`, `ITSecurityAuditor` |

**Imports:** `infra.sso`, `infra.db`, `infra.crypto`, `core.clock`, `domain.audit`.
**Complexity:** complex.

#### M8 `domain/notifications`

| Item | Path | Test path | Complexity |
|---|---|---|---|
| `domain/notifications/service.py` send / send_batch / list_failed / resend | `backend/src/app/domain/notifications/service.py` | `backend/tests/unit/notifications/`, `backend/tests/integration/notifications/` | moderate |
| `domain/notifications/resubmit.py` ResubmitRequestService | `backend/src/app/domain/notifications/resubmit.py` | `backend/tests/unit/notifications/test_resubmit.py` | moderate |
| `domain/notifications/templates/*.txt` Jinja email bodies | `backend/src/app/domain/notifications/templates/` | golden file tests | simple |
| `domain/notifications/models.py` Notification + ResubmitRequest ORM | `backend/src/app/domain/notifications/models.py` | n/a | simple |
| `api/v1/notifications.py` list/resend + resubmit endpoints | `backend/src/app/api/v1/notifications.py` | `backend/tests/api/test_notifications.py` | moderate |

**Exports (M8)**

| Symbol | Signature |
|---|---|
| `NotificationService.send` | `async (template: str, recipient_id: UUID, context: dict, related: tuple[str, UUID] \| None = None) -> Notification` |
| `NotificationService.send_batch` | `async (template: str, recipient_ids: list[UUID], context: dict, related: tuple[str, UUID] \| None = None) -> list[Notification]` |
| `NotificationService.list_failed` | `async (limit: int = 100) -> list[Notification]` |
| `NotificationService.resend` | `async (notification_id: UUID) -> Notification` |
| `ResubmitRequestService.create` | `async (cycle_id: UUID, org_unit_id: UUID, requester_id: UUID, reason: str, target_version: int \| None = None) -> ResubmitRequest` |
| `ResubmitRequestService.list` | `async (cycle_id: UUID, org_unit_id: UUID) -> list[ResubmitRequest]` |
| `NotificationType` | enum (matches DB enum) |

**Imports:** `infra.email`, `infra.db`, `core.clock`, `domain.audit`, `core.security`.
**Complexity:** moderate.

### Batch 3 — Accounts (M2)

| Item | Path | Test path | Complexity |
|---|---|---|---|
| `domain/accounts/service.py` AccountService CRUD + import_actuals | `backend/src/app/domain/accounts/service.py` | `backend/tests/unit/accounts/`, `backend/tests/integration/accounts/` | complex |
| `domain/accounts/validator.py` row validation for actuals | `backend/src/app/domain/accounts/validator.py` | `backend/tests/unit/accounts/test_validator.py` | moderate |
| `domain/accounts/models.py` AccountCode + ActualExpense ORM | `backend/src/app/domain/accounts/models.py` | n/a | simple |
| `domain/_shared/queries.py` `org_unit_code_to_id_map` (§5.4) | `backend/src/app/domain/_shared/queries.py` | `backend/tests/unit/_shared/test_queries.py` | simple |
| `domain/_shared/row_validation.py` (§5.3) | `backend/src/app/domain/_shared/row_validation.py` | `backend/tests/unit/_shared/test_row_validation.py` | moderate |
| `api/v1/accounts.py` accounts + actuals routes | `backend/src/app/api/v1/accounts.py` | `backend/tests/api/test_accounts.py` | moderate |

**Exports (M2 + `_shared`)**

| Symbol | Signature |
|---|---|
| `AccountService.list` | `async (category: AccountCategory \| None = None) -> list[AccountCode]` |
| `AccountService.upsert` | `async (data: AccountCodeWrite) -> AccountCode` |
| `AccountService.get_by_code` | `async (code: str) -> AccountCode` |
| `AccountService.get_operational_codes_set` | `async () -> set[str]` |
| `AccountService.get_codes_by_category` | `async (category: AccountCategory) -> set[str]` |
| `AccountService.import_actuals` | `async (cycle_id: UUID, filename: str, content: bytes, user: User) -> ImportSummary` |
| `AccountCategory` | StrEnum: `operational`, `personnel`, `shared_cost` |
| `RowError`, `ValidationResult`, `clean_cell`, `parse_amount`, `AmountParseError` | (§5.3) |
| `org_unit_code_to_id_map` | `async (db) -> dict[str, UUID]` |

**Imports:** `infra.db`, `infra.tabular`, `infra.storage`, `domain._shared.row_validation`, `domain._shared.queries`, `domain.audit`, `core.security`.
**Complexity:** complex.

### Batch 4 — Cycles (M1)

| Item | Path | Test path | Complexity |
|---|---|---|---|
| `domain/cycles/service.py` create/open/close/reopen/get/list_filing_units/assert_open | `backend/src/app/domain/cycles/service.py` | `backend/tests/unit/cycles/`, `backend/tests/integration/cycles/` | complex |
| `domain/cycles/reminders.py` set_reminder_schedule + dispatch_deadline_reminders + cron registration callback | `backend/src/app/domain/cycles/reminders.py` | `backend/tests/integration/cycles/test_reminders.py` | complex |
| `domain/cycles/state_machine.py` Draft/Open/Closed transitions | `backend/src/app/domain/cycles/state_machine.py` | `backend/tests/unit/cycles/test_state_machine.py` | simple |
| `domain/cycles/models.py` BudgetCycle + CycleReminderSchedule + OrgUnit ORM | `backend/src/app/domain/cycles/models.py` | n/a | simple |
| `domain/cycles/filing_units.py` resolve filing units, manager check (FR-002) | `backend/src/app/domain/cycles/filing_units.py` | `backend/tests/unit/cycles/test_filing_units.py` | moderate |
| `infra/db/repos/budget_uploads_query.py` `unsubmitted_for_cycle` shared SQL helper used by `cycles` reminders + (later) `consolidation` dashboard | `backend/src/app/infra/db/repos/budget_uploads_query.py` | `backend/tests/integration/infra/test_unsubmitted_query.py` | moderate |
| `api/v1/cycles.py` cycle endpoints + admin/org-units endpoints | `backend/src/app/api/v1/cycles.py`, `backend/src/app/api/v1/admin/org_units.py` | `backend/tests/api/test_cycles.py` | complex |

**Exports (M1)**

| Symbol | Signature |
|---|---|
| `CycleService.create` | `async (fiscal_year: int, deadline: date, reporting_currency: str, user: User) -> BudgetCycle` |
| `CycleService.open` | `async (cycle_id: UUID) -> tuple[BudgetCycle, list[OrgUnit]]` (returns the filing-unit list for orchestrator step 3) |
| `CycleService.close` | `async (cycle_id: UUID, user: User) -> BudgetCycle` |
| `CycleService.reopen` | `async (cycle_id: UUID, reason: str, user: User) -> BudgetCycle` |
| `CycleService.get` | `async (cycle_id: UUID) -> BudgetCycle` |
| `CycleService.get_status` | `async (cycle_id: UUID) -> CycleStatus` |
| `CycleService.list_filing_units` | `async (cycle_id: UUID) -> list[FilingUnitInfo]` |
| `CycleService.assert_open` | `async (cycle_id: UUID) -> None` (raises `CYCLE_004` if not Open) |
| `CycleService.set_reminder_schedule` | `async (cycle_id: UUID, days_before: list[int]) -> list[CycleReminderSchedule]` |
| `CycleService.dispatch_deadline_reminders` | `async () -> DispatchSummary` (cron callback) |
| `CycleStatus` | StrEnum: `draft`/`open`/`closed` |
| `FilingUnitInfo` | Pydantic: `org_unit_id`, `code`, `name`, `has_manager`, `warnings` |

**Imports:** `domain.notifications`, `domain.audit`, `core.security`, `infra.db`, `infra.scheduler`, `core.clock`.
**Complexity:** complex.

### Batch 5 — Upload modules (parallel quartet: M3, M4, M5, M6)

These four modules have no inter-dependency and only share dependencies on cycles, accounts, notifications, and `_shared`. Spawn one subagent per module — they MUST follow an identical structural template (validator + service + routes + ORM models).

#### M3 `domain/templates`

| Item | Path | Test path | Complexity |
|---|---|---|---|
| `domain/templates/service.py` generate_for_cycle / regenerate / download | `backend/src/app/domain/templates/service.py` | `backend/tests/unit/templates/`, `backend/tests/integration/templates/` | complex |
| `domain/templates/builder.py` openpyxl workbook builder (operational accounts only, prefilled actuals) | `backend/src/app/domain/templates/builder.py` | `backend/tests/unit/templates/test_builder.py` | complex |
| `domain/templates/models.py` ExcelTemplate ORM | `backend/src/app/domain/templates/models.py` | n/a | simple |
| `api/v1/templates.py` regenerate + download routes | `backend/src/app/api/v1/templates.py` | `backend/tests/api/test_templates.py` | moderate |

**Exports (M3)**

| Symbol | Signature |
|---|---|
| `TemplateService.generate_for_cycle` | `async (cycle: BudgetCycle, filing_units: list[OrgUnit], user: User) -> list[TemplateGenerationResult]` |
| `TemplateService.regenerate` | `async (cycle_id: UUID, org_unit_id: UUID, user: User) -> TemplateGenerationResult` |
| `TemplateService.download` | `async (cycle_id: UUID, org_unit_id: UUID, user: User) -> tuple[str, bytes]` (filename, bytes) |
| `TemplateGenerationResult` | Pydantic: `org_unit_id`, `status`, `error?` |

**Imports:** `domain.cycles`, `domain.accounts`, `domain.audit`, `core.security`, `infra.excel`, `infra.storage`.
**Complexity:** complex.

#### M4 `domain/budget_uploads`

| Item | Path | Test path | Complexity |
|---|---|---|---|
| `domain/budget_uploads/service.py` upload / list_versions / get / get_latest | `backend/src/app/domain/budget_uploads/service.py` | `backend/tests/unit/budget_uploads/`, `backend/tests/integration/budget_uploads/` | complex |
| `domain/budget_uploads/validator.py` BudgetUploadValidator (size, rows, dept code, required cells, amount) | `backend/src/app/domain/budget_uploads/validator.py` | `backend/tests/unit/budget_uploads/test_validator.py` | complex |
| `domain/budget_uploads/models.py` BudgetUpload + BudgetLine ORM | `backend/src/app/domain/budget_uploads/models.py` | n/a | simple |
| `api/v1/budget_uploads.py` POST/GET routes | `backend/src/app/api/v1/budget_uploads.py` | `backend/tests/api/test_budget_uploads.py` | moderate |

**Exports (M4)**

| Symbol | Signature |
|---|---|
| `BudgetUploadService.upload` | `async (cycle_id: UUID, org_unit_id: UUID, filename: str, content: bytes, user: User) -> BudgetUpload` |
| `BudgetUploadService.list_versions` | `async (cycle_id: UUID, org_unit_id: UUID) -> list[BudgetUpload]` |
| `BudgetUploadService.get` | `async (upload_id: UUID) -> BudgetUpload` |
| `BudgetUploadService.get_latest` | `async (cycle_id: UUID, org_unit_id: UUID) -> BudgetUpload \| None` |
| `BudgetUploadService.get_latest_by_cycle` | `async (cycle_id: UUID) -> dict[tuple[UUID, UUID], Decimal]` (consumed by `consolidation`) |
| `BudgetUploadValidator.validate` | `(workbook, *, expected_dept_code: str, operational_codes: set[str]) -> ValidationResult` |

**Imports:** `domain.cycles`, `domain.accounts`, `domain.notifications`, `domain.audit`, `core.security`, `domain._shared.row_validation`, `infra.excel`, `infra.storage`, `infra.db.helpers.next_version`.
**Complexity:** complex.

#### M5 `domain/personnel`

| Item | Path | Test path | Complexity |
|---|---|---|---|
| `domain/personnel/service.py` import_ / list_versions / get | `backend/src/app/domain/personnel/service.py` | `backend/tests/unit/personnel/`, `backend/tests/integration/personnel/` | moderate |
| `domain/personnel/validator.py` PersonnelImportValidator | `backend/src/app/domain/personnel/validator.py` | `backend/tests/unit/personnel/test_validator.py` | moderate |
| `domain/personnel/models.py` PersonnelBudgetUpload + Line ORM | `backend/src/app/domain/personnel/models.py` | n/a | simple |
| `api/v1/personnel.py` POST/GET routes | `backend/src/app/api/v1/personnel.py` | `backend/tests/api/test_personnel.py` | moderate |

**Exports (M5)**

| Symbol | Signature |
|---|---|
| `PersonnelImportService.import_` | `async (cycle_id: UUID, filename: str, content: bytes, user: User) -> PersonnelBudgetUpload` |
| `PersonnelImportService.list_versions` | `async (cycle_id: UUID) -> list[PersonnelBudgetUpload]` |
| `PersonnelImportService.get` | `async (upload_id: UUID) -> PersonnelBudgetUpload` |
| `PersonnelImportService.get_latest_by_cycle` | `async (cycle_id: UUID) -> dict[tuple[UUID, UUID], Decimal]` |
| `PersonnelImportValidator.validate` | `(rows: list[dict], *, org_unit_codes: dict[str, UUID], personnel_codes: set[str]) -> ValidationResult` |

**Imports:** `domain.cycles`, `domain.accounts`, `domain.notifications`, `domain.audit`, `core.security`, `domain._shared`, `infra.tabular`, `infra.storage`, `infra.db.helpers.next_version`.
**Complexity:** moderate.

#### M6 `domain/shared_costs`

| Item | Path | Test path | Complexity |
|---|---|---|---|
| `domain/shared_costs/service.py` import_ / list_versions / get / diff_affected_units | `backend/src/app/domain/shared_costs/service.py` | `backend/tests/unit/shared_costs/`, `backend/tests/integration/shared_costs/` | moderate |
| `domain/shared_costs/validator.py` SharedCostImportValidator | `backend/src/app/domain/shared_costs/validator.py` | `backend/tests/unit/shared_costs/test_validator.py` | moderate |
| `domain/shared_costs/models.py` SharedCostUpload + Line ORM | `backend/src/app/domain/shared_costs/models.py` | n/a | simple |
| `api/v1/shared_costs.py` POST/GET routes | `backend/src/app/api/v1/shared_costs.py` | `backend/tests/api/test_shared_costs.py` | moderate |

**Exports (M6)**

| Symbol | Signature |
|---|---|
| `SharedCostImportService.import_` | `async (cycle_id: UUID, filename: str, content: bytes, user: User) -> SharedCostUpload` |
| `SharedCostImportService.list_versions` | `async (cycle_id: UUID) -> list[SharedCostUpload]` |
| `SharedCostImportService.get` | `async (upload_id: UUID) -> SharedCostUpload` |
| `SharedCostImportService.get_latest_by_cycle` | `async (cycle_id: UUID) -> dict[tuple[UUID, UUID], Decimal]` |
| `SharedCostImportService.diff_affected_units` | `(prev_lines, new_lines) -> list[UUID]` (for FR-029 notification scope) |
| `SharedCostImportValidator.validate` | `(rows, *, org_unit_codes, shared_cost_codes) -> ValidationResult` |

**Imports:** identical to M5 (just `personnel` → `shared_costs` and category swap).
**Complexity:** moderate.

### Batch 6 — Consolidation + API surface + open-cycle orchestrator (M7 + M11 tail)

M7 is one module but the architecture flags it as splittable into 3 files. M11 is a single thin orchestrator that consolidates leftover routes — it merges into this batch per the rule that single-module CLI/wrappers join the last real batch.

| Item | Path | Test path | Complexity |
|---|---|---|---|
| `domain/consolidation/dashboard.py` DashboardService.status_for_user | `backend/src/app/domain/consolidation/dashboard.py` | `backend/tests/unit/consolidation/test_dashboard.py`, `backend/tests/integration/consolidation/` | complex |
| `domain/consolidation/report.py` ConsolidatedReportService.build (FR-015 + FR-016) | `backend/src/app/domain/consolidation/report.py` | `backend/tests/unit/consolidation/test_report.py` | complex |
| `domain/consolidation/export.py` `.export_async` + `ReportExportHandler` (registered with `infra/jobs`) | `backend/src/app/domain/consolidation/export.py` | `backend/tests/integration/consolidation/test_export.py` | complex |
| `api/v1/dashboard.py` GET dashboard | `backend/src/app/api/v1/dashboard.py` | `backend/tests/api/test_dashboard.py` | moderate |
| `api/v1/reports.py` GET consolidated + POST export + status + file | `backend/src/app/api/v1/reports.py` | `backend/tests/api/test_reports.py` | moderate |
| `api/v1/router.py` aggregate every router; mount under `/api/v1` | `backend/src/app/api/v1/router.py` | `backend/tests/api/test_router.py` | simple |
| `api/v1/orchestrators/open_cycle.py` Step 1–5 pipeline (RBAC → CycleService.open → TemplateService.generate_for_cycle → NotificationService.send_batch → response) | `backend/src/app/api/v1/orchestrators/open_cycle.py` | `backend/tests/api/test_open_cycle_pipeline.py` | complex |
| `api/v1/admin/__init__.py` admin sub-router (org_units, users, accounts) | `backend/src/app/api/v1/admin/__init__.py` | n/a | simple |
| Pydantic request/response schemas for all endpoints | `backend/src/app/schemas/*.py` | `backend/tests/unit/schemas/` | moderate |
| `app/deps.py` FastAPI dependency providers (db session, current_user, services) | `backend/src/app/deps.py` | `backend/tests/api/test_deps.py` | moderate |

**Exports (M7)**

| Symbol | Signature |
|---|---|
| `DashboardService.status_for_user` | `async (cycle_id: UUID, user: User) -> DashboardResponse` |
| `ConsolidatedReportService.build` | `async (cycle_id: UUID, scope: ReportScope) -> ConsolidatedReport` |
| `ConsolidatedReportService.export_async` | `async (cycle_id: UUID, scope: ReportScope, format: ExportFormat, user: User) -> ExportEnqueueResult` |
| `ReportExportHandler.run` | `async (job_payload: dict) -> dict` (registered as job handler at startup) |
| `DashboardResponse`/`ConsolidatedReport`/`ConsolidatedReportRow`/`ReportScope`/`ExportFormat` | Pydantic models |

**Imports:** `domain.cycles`, `domain.budget_uploads`, `domain.personnel`, `domain.shared_costs`, `domain.accounts`, `domain.audit`, `core.security`, `infra.db`, `infra.jobs`, `infra.excel`, `infra.storage`, `infra.db.repos.budget_uploads_query.unsubmitted_for_cycle`.
**Complexity:** complex.

### Batches 7–8 — Frontend (deferred / out of backend scope)

These are listed for completeness against architecture §9 Batch Sequence but are NOT executed by the backend build pipeline. A separate orchestration spawns the frontend build once Batch 6 is green.

- **Batch 7** — Frontend foundation: Vite + React Router + Mantine theme + i18n + TanStack Query + axios cookie auth + `/auth/me`
- **Batch 8** — Frontend feature pages: 11 pages from architecture §5.13 — each page maps to one backend feature batch

### Total batches: 7 backend (Batch 0–6) + 2 frontend (deferred)

Backend 7 batches over 11 backend modules ≈ 1.6 modules per batch on average. Within the constraint ⌈12/6⌉ = 2 minimum, this respects the dependency chain (audit → security → cycles → uploads → consolidation) which is irreducible. The fan-out batches (Batch 2, Batch 5) absorb the otherwise-trivial single-module batches.

## 7. Ambiguities

These items in the PRD/architecture need product or tech-lead clarification before or during implementation. Ambiguity does not block — defaults are noted, but flag at review.

1. **Type checker mismatch.** The user task (this build prompt) says `mypy`; architecture §1 locks `pyright`. **Decision needed.** Default in this plan: pyright (architecture wins because it's the source of dependency pinning). If mypy is preferred, swap `pyright` for `mypy` in §1 and add `mypy` to deps; the rest of the plan is unaffected because both consume the same `X | None`/PEP 604 type hints.
2. **Formatter mismatch.** User task says `black`; architecture §1 says `ruff format` (and explicitly states ruff replaces black). Default: `ruff format`. Same swap rule as item 1.
3. **Package manager.** User task says `pip + venv` (or `uv if preferred`); architecture says `uv`. Default: `uv`. If unavailable, fall back to `pip + venv` and a hand-maintained `requirements.txt` — no plan changes other than commands.
4. **FR-011 dept code field name.** The FR says "部門代碼一致" but does not specify the spreadsheet column header — `dept_code`, `org_unit_code`, or a Chinese header? Default: assume the template generator (FR-009) writes a fixed cell address (e.g. `B2`) and the validator reads that same cell, sidestepping the header-name question.
5. **FR-024/027 dept_id meaning.** The CSV/Excel column is called `dept_id` in the PRD prose but `org_unit.code` is the user-facing identifier (e.g. "4023"). Is `dept_id` the human code or the internal UUID? Default: it is the human-readable `org_unit.code` (4–6 digit string), and `_shared/queries.org_unit_code_to_id_map` translates it. Document this in importer error messages.
6. **FR-002 "explicit exclusion".** PRD says blocking until "補齊或明確排除" — there is no API surface defined for "explicitly excluding" a manager-less filing unit from a cycle. Default: add a flag column `excluded_for_cycle_ids JSONB` (or join table) on `org_units`; expose `PATCH /admin/org-units/{id}` to set; cycle-open re-checks. Architecture does not specify this — flag for review.
7. **FR-017 sync vs async threshold.** Architecture says >1000 units routes to async; PRD says ">1000 單位 改以非同步排程". Same number. But the sync-export response shape differs from async (file URL vs job_id). Default: sync returns 201 with `{ file_url, expires_at }`; async returns 202 with `{ job_id }`. Document in OpenAPI.
8. **FR-005 first-class reminder enable/disable.** PRD says "可設定提醒排程" but does not say whether reminders are opt-in or default-on. Default: default-on with `[7, 3, 1]` days_before, configurable via PATCH endpoint. Allow empty list to disable.
9. **FR-029 "affected" definition.** PRD says notify departments "公攤金額有異動的". Diff against the previous version's lines. Default: `diff_affected_units` returns the symmetric difference of `(org_unit_id, account_code_id, amount)` between previous and new — any change in amount counts; new dept counts; removed dept counts. Notify the manager of each affected `org_unit_id`.
10. **FR-021 fallback when SSO is down.** PRD says return "驗證服務暫時無法使用" (AUTH_001 / 503). No fallback path. Confirmed: there is NO local-account fallback. Document this in the runbook.
11. **FR-023 retention enforcement.** Schema preserves rows indefinitely; architecture says "5-year retention enforced by an offline retention job". This job is not in the implementation plan. Default: out of scope for build; document the requirement in Operations runbook for Enterprise IT.
12. **Currency conversion.** PRD §2.3 says multi-currency is out of scope for Phase 1 but `BudgetCycle.reporting_currency` is on the entity. Default: store the value, validate as ISO 4217 3-letter, do not convert. Default `TWD`.
