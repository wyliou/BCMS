# Spec: alembic_baseline

Module: `backend/alembic/versions/0001_baseline.py`
Tests: `backend/tests/integration/test_migrations.py`

## FRs

All FRs indirectly — this migration creates the schema that all domain modules depend on.

## Purpose

Single Alembic migration that creates all 18 tables (15 from PRD §10 + 3 architecture-added) from scratch. This is the baseline for a greenfield database. `upgrade()` must be idempotent via `IF NOT EXISTS` guards where appropriate. `downgrade()` must reverse all DDL in reverse order.

## 18 Tables (from architecture §6)

1. `org_units` — OrgUnit
2. `users` — User (encrypted columns)
3. `sessions` — Session (architecture-added)
4. `account_codes` — AccountCode
5. `budget_cycles` — BudgetCycle
6. `cycle_reminder_schedules` — CycleReminderSchedule (architecture-added)
7. `actual_expenses` — ActualExpense
8. `excel_templates` — ExcelTemplate (encrypted `file_path_enc`)
9. `budget_uploads` — BudgetUpload (encrypted `file_path_enc`)
10. `budget_lines` — BudgetLine
11. `personnel_budget_uploads` — PersonnelBudgetUpload (encrypted `file_path_enc`)
12. `personnel_budget_lines` — PersonnelBudgetLine
13. `shared_cost_uploads` — SharedCostUpload (encrypted `file_path_enc`)
14. `shared_cost_lines` — SharedCostLine
15. `resubmit_requests` — ResubmitRequest
16. `notifications` — Notification
17. `audit_logs` — AuditLog (append-only; UPDATE/DELETE revoked)
18. `job_runs` — JobRun (architecture-added)

## Enum Types (PostgreSQL `CREATE TYPE`)

Must be created BEFORE the tables that reference them (in `upgrade()`):

| Enum name | Values |
|---|---|
| `cycle_status` | `'draft'`, `'open'`, `'closed'` |
| `upload_status` | `'pending'`, `'valid'`, `'invalid'` |
| `notification_type` | `'cycle_opened'`, `'upload_confirmed'`, `'resubmit_requested'`, `'deadline_reminder'`, `'personnel_imported'`, `'shared_cost_imported'` |
| `notification_status` | `'queued'`, `'sent'`, `'failed'`, `'bounced'` |
| `notification_channel` | `'email'` |
| `account_category` | `'operational'`, `'personnel'`, `'shared_cost'` |
| `org_level_code` | `'0000'`, `'0500'`, `'0800'`, `'1000'`, `'2000'`, `'4000'`, `'5000'`, `'6000'` |
| `job_status` | `'queued'`, `'running'`, `'succeeded'`, `'failed'` |

## DDL Summary per Table

All DDL must exactly match architecture §6. Key constraints excerpted below.

### Extensions + Trigger

```sql
-- In upgrade():
op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
op.execute("""
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")
```

### Critical Constraints (must not be missed)

- `org_units`: `UNIQUE(code)`, `CHECK (NOT (is_filing_unit AND is_reviewer_only))`, `idx_org_units_filing` partial index.
- `users`: `UNIQUE(sso_id_hash)`, `UNIQUE(email_hash)`. Columns `sso_id_enc BYTEA`, `email_enc BYTEA`.
- `budget_cycles`: Partial unique index `uq_budget_cycles_active_year ON budget_cycles(fiscal_year) WHERE status IN ('draft', 'open')` — this is the FR-001 guard.
- `budget_uploads`: `UNIQUE(cycle_id, org_unit_id, version)`, `CHECK(file_size_bytes <= 10485760)`, `CHECK(row_count <= 5000)`.
- `budget_lines`: `CHECK(amount >= 0)`, `UNIQUE(upload_id, account_code_id)`.
- `personnel_budget_lines`: `CHECK(amount > 0)`, `UNIQUE(upload_id, org_unit_id, account_code_id)`.
- `shared_cost_lines`: `CHECK(amount > 0)`, `UNIQUE(upload_id, org_unit_id, account_code_id)`.
- `audit_logs`: `BIGSERIAL sequence_no UNIQUE`, `REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC`.
- `cycle_reminder_schedules`: `UNIQUE(cycle_id, days_before)`, `CHECK(days_before > 0)`.

### ON DELETE Policies

- Line tables (`budget_lines`, `personnel_budget_lines`, `shared_cost_lines`): `ON DELETE CASCADE` on `upload_id` FK.
- All other FKs: `ON DELETE RESTRICT` (default).
- `sessions.user_id`: `ON DELETE CASCADE` (session deleted when user is deleted).

### Updated_at triggers

Apply `trg_{table}_updated BEFORE UPDATE ... FOR EACH ROW EXECUTE FUNCTION set_updated_at()` on all tables with `updated_at` column: `org_units`, `users`, `account_codes`, `budget_cycles`, `actual_expenses`.

## Imports (Alembic migration file)

```python
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
```

## Alembic Metadata

```python
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None
```

## `downgrade()` Order

Drop tables in reverse dependency order (children before parents):

1. Drop all triggers.
2. Drop tables: `job_runs`, `audit_logs`, `notifications`, `resubmit_requests`, `shared_cost_lines`, `shared_cost_uploads`, `personnel_budget_lines`, `personnel_budget_uploads`, `budget_lines`, `budget_uploads`, `excel_templates`, `actual_expenses`, `cycle_reminder_schedules`, `budget_cycles`, `account_codes`, `sessions`, `users`, `org_units`.
3. Drop enum types (reverse of creation order).
4. Drop `set_updated_at` function.
5. Drop `pgcrypto` extension (optional — extension drop may be skipped in shared environments).

## Gotchas

- **Partial unique index** on `budget_cycles` cannot be expressed with plain Alembic `op.create_index` — use `op.execute(raw_sql)` for the partial index.
- **REVOKE on `audit_logs`** must be an `op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC")` call.
- **BIGSERIAL** maps to `sa.BigInteger` with `server_default=sa.text("nextval('audit_logs_sequence_no_seq')")` after creating the sequence. Alembic's `sa.BigInteger` with `autoincrement=True` generates `BIGSERIAL` in PostgreSQL dialect.
- **BYTEA columns** map to `sa.LargeBinary()` in SQLAlchemy.
- **JSONB columns** map to `postgresql.JSONB`.
- **INET** maps to `postgresql.INET`.
- **TIMESTAMPTZ** maps to `sa.DateTime(timezone=True)`.
- Keep this file under 500 lines: use helper functions `_create_enums()`, `_drop_enums()`, `_create_triggers(op)` to break up the `upgrade()` body.

## Consistency Constraints

- **CR-001 Stage B check:** *"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
  - Not directly applicable (no Python application logic), but the schema constraints enforce DB-level guards.

## Tests

### `test_migrations.py` (integration — requires Postgres)

1. `test_upgrade_head_succeeds` — run `alembic upgrade head` on a fresh DB; assert no exception.
2. `test_all_18_tables_exist` — after upgrade, inspect DB for all 18 table names.
3. `test_partial_unique_index_enforced` — insert two rows in `budget_cycles` with same `fiscal_year` and `status='open'`; assert `IntegrityError`.
4. `test_audit_logs_revoke_enforced` — attempt `UPDATE audit_logs SET action='x' WHERE ...`; assert permission denied (when using the application DB role).
5. `test_downgrade_succeeds` — run `alembic downgrade base`; assert all tables dropped.
6. `test_upgrade_downgrade_upgrade_idempotent` — upgrade → downgrade → upgrade; assert clean state each direction.
