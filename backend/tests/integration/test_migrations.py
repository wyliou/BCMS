"""Integration tests for the Alembic baseline migration (requires Postgres)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import skip_unless_postgres

pytestmark = [pytest.mark.integration, skip_unless_postgres]


_EXPECTED_TABLES = {
    "org_units",
    "users",
    "sessions",
    "account_codes",
    "budget_cycles",
    "cycle_reminder_schedules",
    "actual_expenses",
    "excel_templates",
    "budget_uploads",
    "budget_lines",
    "personnel_budget_uploads",
    "personnel_budget_lines",
    "shared_cost_uploads",
    "shared_cost_lines",
    "resubmit_requests",
    "notifications",
    "audit_logs",
    "job_runs",
}


async def test_all_baseline_tables_exist(db_session: AsyncSession) -> None:
    """Every table declared in architecture §6 is present after migration."""
    result = await db_session.execute(
        text("SELECT table_name FROM information_schema.tables " "WHERE table_schema = 'public'")
    )
    names = {row[0] for row in result.all()}
    missing = _EXPECTED_TABLES - names
    assert not missing, f"Missing tables after migration: {missing}"


async def test_partial_unique_index_on_budget_cycles(
    db_session: AsyncSession,
) -> None:
    """The FR-001 partial unique index exists."""
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'budget_cycles' "
            "AND indexname = 'uq_budget_cycles_active_year'"
        )
    )
    assert result.first() is not None
