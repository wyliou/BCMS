"""Integration tests for :mod:`app.domain.accounts.service.AccountService`.

Requires a live Postgres backend — skipped when none is reachable via
``BC_DATABASE_URL``. Exercises the real ORM round-trip for upsert,
list, and the actuals importer.
"""

from __future__ import annotations

import csv
import io
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_utc
from app.core.security.models import OrgUnit, User
from app.core.security.roles import Role
from app.domain.accounts.models import AccountCategory, AccountCode, ActualExpense
from app.domain.accounts.service import AccountCodeWrite, AccountService
from tests.integration.conftest import skip_unless_postgres

pytestmark = [pytest.mark.integration, skip_unless_postgres]


async def _seed_user(db: AsyncSession) -> User:
    """Insert a SystemAdmin user for the integration tier and return it."""
    user = User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=uuid4().bytes.ljust(32, b"\x00"),
        name="Integration Tester",
        email_enc=b"",
        email_hash=uuid4().bytes.ljust(32, b"\x00"),
        roles=[Role.SystemAdmin.value],
        org_unit_id=None,
        is_active=True,
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db.add(user)
    await db.flush()
    return user


async def test_upsert_and_list_round_trip(db_session: AsyncSession) -> None:
    """Upsert inserts a row and ``list()`` returns it."""
    service = AccountService(db_session)
    user = await _seed_user(db_session)

    body = AccountCodeWrite(
        code=f"TEST-{uuid4().hex[:6]}",
        name="Integration test",
        category=AccountCategory.operational,
        level=1,
    )
    try:
        row = await service.upsert(data=body, user=user)
        assert row.code == body.code
        listed = await service.list(category=AccountCategory.operational)
        assert any(r.code == body.code for r in listed)
    finally:
        await db_session.execute(delete(AccountCode).where(AccountCode.code == body.code))
        await db_session.commit()


async def test_import_actuals_round_trip(db_session: AsyncSession) -> None:
    """Import a 1-row CSV and assert an ``actual_expenses`` row was written."""
    service = AccountService(db_session)
    user = await _seed_user(db_session)

    account_code = f"TEST-{uuid4().hex[:6]}"
    body = AccountCodeWrite(
        code=account_code,
        name="Integration test",
        category=AccountCategory.operational,
        level=1,
    )
    await service.upsert(data=body, user=user)

    # Need a filing org unit; grab any existing one.
    org_row = (await db_session.execute(select(OrgUnit).limit(1))).scalar_one_or_none()
    if org_row is None:
        pytest.skip("No org_units seeded — skipping actuals import test")

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["org_unit_code", "account_code", "amount"])
    writer.writeheader()
    writer.writerow(
        {
            "org_unit_code": org_row.code,
            "account_code": account_code,
            "amount": "42.50",
        }
    )
    content = buf.getvalue().encode("utf-8")

    # Need a cycle_id — seed a minimal cycle row via direct SQL would be
    # intrusive. Skip when no cycles table is reachable via ORM in Batch 3.
    try:
        from app.domain.cycles.models import BudgetCycle  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("domain.cycles not yet shipped — Batch 4 integration")
        return

    cycle = BudgetCycle(
        id=uuid4(),
        fiscal_year=2099,
        deadline=now_utc().date(),
        status="open",
        created_by=user.id,
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db_session.add(cycle)
    await db_session.flush()
    try:
        summary = await service.import_actuals(
            cycle_id=cycle.id,
            filename="actuals.csv",
            content=content,
            user=user,
        )
        assert summary.rows_imported == 1
        rows = (
            (
                await db_session.execute(
                    select(ActualExpense).where(ActualExpense.cycle_id == cycle.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
    finally:
        await db_session.execute(delete(ActualExpense).where(ActualExpense.cycle_id == cycle.id))
        await db_session.execute(delete(AccountCode).where(AccountCode.code == account_code))
        await db_session.commit()
