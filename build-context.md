# BCMS Build Context

Cross-cutting conventions, patterns, and constraints that apply to every batch and every module. Tech Lead delegation prompts reference this document instead of repeating these rules.

## Stack

| Layer | Choice | Version | Source |
|---|---|---|---|
| Language | Python | 3.12 (≥3.11 acceptable) | architecture §1 |
| Web framework | FastAPI | 0.115.x | architecture §1 |
| ASGI server | Uvicorn + Gunicorn workers | 0.32.x / 23.x | architecture §1 |
| Data validation | Pydantic | 2.9.x | architecture §1 |
| ORM | SQLAlchemy (async) | 2.0.x | architecture §1 |
| Migrations | Alembic | 1.13.x | architecture §1 |
| DB driver | asyncpg | 0.30.x | architecture §1 |
| Database | PostgreSQL | 16 | architecture §1 |
| Auth — OIDC/SAML | Authlib | 1.3.x | architecture §1 |
| Auth — JWT | PyJWT | 2.9.x | architecture §1 |
| Excel | openpyxl | 3.1.x | architecture §1 |
| CSV | stdlib `csv` | — | architecture §1 |
| Email | aiosmtplib | 3.0.x | architecture §1 |
| Cron | APScheduler | 3.10.x (cron only) | architecture §1 |
| Durable jobs | DB-backed `job_runs` table + custom worker | — | architecture §1 |
| Cryptography | cryptography | 43.x | architecture §1 |
| Logging | structlog | 24.x | architecture §1 |
| Testing | pytest + pytest-asyncio + httpx | 8.x / 0.24 / 0.27 | architecture §1 |
| Lint + format | ruff | 0.7.x (replaces black/flake8/isort) | architecture §1 |
| Type check | pyright | 1.1.x (strict mode for `src/`) | architecture §1 |
| Package manager | uv | 0.5.x | architecture §1 |

If the project enforces global conventions of mypy + black, swap them in (see build-plan §7 Ambiguities item 1–2). The plan is otherwise unaffected.

## Source Layout

- All backend code lives under `backend/src/app/`.
- All backend tests under `backend/tests/{unit,integration,api,fixtures}/`.
- ORM models live next to the domain module that owns the table (e.g. `app/domain/budget_uploads/models.py`), NOT in a global `app/models/` package.
- Pydantic request/response schemas live in `app/schemas/<resource>.py` separate from ORM models.
- `app/api/v1/` is thin orchestration only — no business logic, no math, no parsing, no path construction.
- `app/infra/*` are side-effect adapters; domain code calls them through dependency injection, never directly via library imports.
- `app/domain/_shared/` is private to the domain layer; `api/v1` and `infra/*` MUST NOT import from it.

## Error Handling Strategy

Two patterns coexist (per architecture §3 Error Propagation):

1. **Raise immediate** — single fatal error (auth failure, RBAC, wrong cycle state, not found, infra failure). Raise an `AppError` subclass from `core.errors`. The global FastAPI exception handler (`app/main.py`) converts it to the JSON envelope `{ "error": {"code", "message", "details"}, "request_id" }` with the HTTP status from the registry, and writes an audit log entry when applicable (FR-022 403 / FR-021 401).
2. **Collect-then-report** — multi-row validation (FR-008, FR-011, FR-024, FR-027). The validator returns `ValidationResult(rows, errors)` from `domain/_shared/row_validation`. If `not result.valid`, the service raises `BatchValidationError(code=...UPLOAD_007|PERS_004|SHARED_004|ACCOUNT_002, errors=result.errors)`. **Integral commit semantics:** zero rows persisted on any failure.

Module conventions:
- `domain/*` services raise `AppError` subclasses; never return error tuples or `None`-as-error.
- `api/v1/*` route handlers do NOT catch domain exceptions; they propagate to the global handler.
- `infra/*` modules wrap library exceptions into `AppError` (e.g. `asyncpg.ConnectionError → SYS_001`).
- The global handler ensures every error response carries `X-Request-ID` and that `domain/audit` records 401/403 outcomes.

Error code registry: every code defined exactly once in `app/core/errors.py` with `(http_status, message_template)`. New codes added by appending to the registry — never inline literals in services.

## Logging Pattern

- **Library:** `structlog`, JSON to stdout.
- **Mandatory fields on every entry:** `timestamp` (ISO-8601 UTC), `level`, `event` (snake_case noun.verb), `request_id`, `user_id` (when authenticated), `module`.
- **Format:** Structured kwargs only — never f-string interpolation in event names.
  ```python
  log = structlog.get_logger(__name__)
  log.info("budget_upload.accepted",
           cycle_id=cycle.id, org_unit_id=ou.id,
           upload_id=upload.id, version=upload.version,
           file_hash=upload.file_hash, user_id=user.id)
  ```
- **Levels:**
  - `ERROR` — handled domain failures returned to caller, infra failures
  - `WARN` — degraded states (notification bounce, retry exhausted, scheduler skipped run)
  - `INFO` — state transitions (cycle opened/closed, upload accepted, import completed, login)
  - `DEBUG` — dev only; off in prod via `BC_LOG_LEVEL`
- **NEVER log:** raw passwords, full JWTs, raw uploaded file contents, PII.
- **App logs vs audit logs:** App logs are operational (structlog → stdout). Audit log entries (FR-023) are written to the `audit_logs` table by `domain/audit.AuditService.record`, NOT via structlog. They may share the same `event` value for correlation.

## Test Requirements

- **Test directory:** `backend/tests/{unit,integration,api,fixtures}/`.
- **Test count:** 3–5 tests per public function/method, covering at minimum: (1) happy path, (2) at least one edge case (empty input, boundary value, max size), (3) at least one error path (raises the documented `AppError` subclass with the right code).
- **Validators (`*Validator.validate`)** require additional row-level coverage: one test per `RowError` code the validator can emit (e.g. `UPLOAD_003` dept mismatch, `UPLOAD_004` empty cell, `UPLOAD_005` bad format, `UPLOAD_006` negative amount), each verifying the row number and column on the resulting `RowError`.
- **`tests/unit/`** — pure logic, no DB, no network, no real file I/O. Use the test doubles from `infra/email.fake_smtp`, `infra/sso.fake_sso`, and pytest's `tmp_path` for storage.
- **`tests/integration/`** — real Postgres (testcontainers or docker-compose); one fresh schema per test class. Use Alembic migrations from baseline, never raw SQL DDL in tests.
- **`tests/api/`** — FastAPI `httpx.AsyncClient` against the in-process app; covers route wiring, RBAC dependency, request/response envelope, error envelope shape.
- **Async tests** — use `pytest.mark.asyncio` and `pytest-asyncio` mode `auto`.
- **Clock determinism** — tests patch `app.core.clock.now_utc` rather than monkey-patching `datetime`.
- **Fixtures** — sample Excel/CSV files live under `backend/tests/fixtures/`. Generated, not committed in binary form; the fixture builder is itself a unit-test module.
- **Fixture scoping** — DB session fixture is `function`-scoped (rollback after each test); SQLAlchemy engine is `session`-scoped; storage tmp dir is `function`-scoped.
- **Singleton teardown** — APScheduler instance and the jobs worker are session-scoped fixtures with explicit `shutdown()` in finalizer to avoid cross-test pollution.
- **Coverage target:** ≥85% line coverage on `app/domain/*` and `app/core/*`; `app/infra/*` is allowed slightly lower (≥75%) because infra is exercised most heavily through integration tests.

## Platform Notes

- **Dev OS:** Windows 10 (this developer); CI and prod target Linux. All paths in source code MUST use forward slashes (POSIX style); never `os.sep`, never raw backslashes. Use `pathlib.Path` for filesystem operations.
- **Shell:** This Bash environment uses Unix shell syntax — `/dev/null`, forward slashes, `:` separator. Subagents MUST NOT introduce Windows-only commands or PowerShell-specific tooling.
- **Line endings:** `.gitattributes` should set `* text=auto eol=lf` for Python sources to avoid CRLF noise. Add this in Batch 0.
- **Encoding:** All files UTF-8. Source files start with no BOM. Test fixtures may include Big5 *negative-test* CSVs to verify the `UTF-8 only` constraint of `infra/csv_io`, but the loader rejects them.
- **Timezone:** Server cron evaluation TZ is `Asia/Taipei` (`BC_TIMEZONE` default), but all stored timestamps are UTC (`TIMESTAMPTZ`). Never store local time.

## Subagent Constraints

**Read this section verbatim into every delegation prompt.**

1. **No stubs.** Every function you commit must have a real implementation. Banned patterns: `raise NotImplementedError`, `# TODO`, `# FIXME`, bare `pass` as a function body, `...` as a function body. The build pipeline runs a stub-scan grep at the end of every batch and rejects PRs containing matches.
2. **No type redefinition.** Reuse the canonical types from `core.errors` (`AppError`, `BatchValidationError`, etc.), `domain/_shared/row_validation` (`RowError`, `ValidationResult`, `clean_cell`, `parse_amount`), `core.security` (`User`, `Role`, `RBAC`), and `infra/db` (`get_session`, `Base`, `next_version`). Do NOT define a local copy with the same name and a slightly different shape.
3. **No new dependencies** beyond the manifest in build-plan §1. If you genuinely need a new library, raise it as a blocker in your delegation reply — do not silently add it to `pyproject.toml`.
4. **No cross-module mocking.** Tests in module A MUST NOT mock module B's internals. Mock only the side-effect adapters listed in §3 Side-Effect Ownership of architecture (`infra/email`, `infra/sso`, `infra/storage`, `infra/scheduler`, `infra/jobs`, `infra/db` session, the clock). Cross-domain calls (e.g. `budget_uploads → notifications.send`) must use the real notifications service against `fake_smtp`, not a mocked `NotificationService`.
5. **Fixture scoping.** DB session fixtures `function`-scoped, engine `session`-scoped, storage tmp dirs `function`-scoped. APScheduler and the jobs worker are session-scoped with explicit teardown.
6. **Singleton teardown.** Anything that registers a cron, opens a DB connection pool, or starts a background worker MUST have a corresponding `shutdown()` / `dispose()` call wired into FastAPI lifespan AND test finalizers. No leaked threads, no leaked file handles between tests.
7. **Files ≤500 lines.** Hard limit on every `.py` file under `backend/src/app/`. If a module hits 400 lines, split per the architecture §4 split plans (e.g. `cycles/` → `service.py` + `reminders.py`; `consolidation/` → `dashboard.py` + `report.py` + `export.py`). Public exports must remain unchanged.
8. **PEP 8** for naming, indentation (4 spaces), import order (stdlib → third-party → local; ruff enforces). Line length 100 chars (ruff config).
9. **Type hints everywhere.** Every function signature has parameter and return type annotations. Use **PEP 604 syntax**: `X | None` (NOT `Optional[X]`), `list[T]` (NOT `List[T]`), `dict[K, V]` (NOT `Dict[K, V]`), `tuple[A, B]` (NOT `Tuple[A, B]`). Use `from __future__ import annotations` only when needed for forward references.
10. **Google-style docstrings** on every public class and function. Sections: `Args:`, `Returns:`, `Raises:`. Skip docstring on private helpers under 5 lines IF the name + signature is self-evident.
11. **No `print()`.** Use `structlog.get_logger(__name__)`. Banned in `src/`; allowed only in scripts under `backend/scripts/`.
12. **No `datetime.now()`.** Use `app.core.clock.now_utc()`. Tests patch the seam.
13. **No direct `open()`** in domain code. Use `infra.storage.save/read/delete`. Path construction is owned by `infra.storage`.
14. **No raw SQL** in domain code. Use SQLAlchemy 2.0 `select()`/`insert()`/`update()` constructs. Raw SQL allowed only in `infra/db/repos/` and Alembic migrations.
15. **Audit AFTER commit, BEFORE return.** Every state-changing service method commits its DB transaction first, then calls `audit.record(...)`, then returns. If the audit write fails, the operation is rolled back and the caller receives an error — we cannot honor FR-023 silently.
16. **RBAC at the route, scope at the service.** Route handlers declare `Depends(RBAC.require_role(...))` and `Depends(RBAC.require_scope(...))`. Services additionally call `RBAC.scoped_org_units(user)` when filtering query results so URL bypass is impossible (FR-022 backend enforcement).
17. **No silent error swallowing.** `except Exception:` is banned outside the global exception handler. Catch specific library exceptions, wrap into `AppError`, and re-raise.
