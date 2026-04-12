"""Integration tests for :class:`app.domain.templates.service.TemplateService`.

Requires a live Postgres backend — skipped when none is reachable via
``BC_DATABASE_URL``. Exercises the real ORM round-trip for
``generate_for_cycle`` + ``download`` using the real :mod:`infra.storage`
pointed at a ``tmp_path`` root.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.clock import now_utc
from app.core.security.models import OrgUnit, User
from app.core.security.roles import Role
from app.domain.accounts.models import AccountCategory, AccountCode
from app.domain.cycles.models import BudgetCycle, CycleState
from app.domain.templates.models import ExcelTemplate
from app.domain.templates.service import TemplateService
from tests.integration.conftest import skip_unless_postgres

pytestmark = [pytest.mark.integration, skip_unless_postgres]


async def _seed_user(db: AsyncSession) -> User:
    """Insert a SystemAdmin user and return it."""
    user = User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=uuid4().bytes.ljust(32, b"\x00"),
        name="Template Integration Tester",
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


async def _seed_cycle(db: AsyncSession, user: User) -> BudgetCycle:
    """Insert an Open :class:`BudgetCycle` and return it."""
    now = now_utc()
    cycle = BudgetCycle(
        fiscal_year=2099,
        deadline=date(2099, 12, 31),
        reporting_currency="TWD",
        status=CycleState.open.value,
        opened_at=now,
        created_by=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(cycle)
    await db.flush()
    return cycle


async def _seed_org_unit(db: AsyncSession) -> OrgUnit:
    """Insert a filing-unit :class:`OrgUnit` and return it."""
    now = now_utc()
    unit = OrgUnit(
        code=f"T{uuid4().hex[:5]}",
        name="Integration Filing Unit",
        level_code="4023",
        parent_id=None,
        is_filing_unit=True,
        is_reviewer_only=False,
        excluded_for_cycle_ids=[],
        created_at=now,
        updated_at=now,
    )
    db.add(unit)
    await db.flush()
    return unit


async def _seed_account(db: AsyncSession, code: str) -> AccountCode:
    """Insert an operational :class:`AccountCode` and return it."""
    now = now_utc()
    row = AccountCode(
        code=code,
        name=f"Account {code}",
        category=AccountCategory.operational,
        level=1,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    return row


async def test_generate_and_download_round_trip(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full generate → persist → download round-trip against real Postgres."""
    monkeypatch.setenv("BC_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()

    user = await _seed_user(db_session)
    cycle = await _seed_cycle(db_session, user)
    unit = await _seed_org_unit(db_session)
    account = await _seed_account(db_session, code=f"INT-{uuid4().hex[:6]}")

    service = TemplateService(db_session)
    try:
        results = await service.generate_for_cycle(
            cycle=cycle,
            filing_units=[unit],
            user=user,
        )
        assert len(results) == 1
        assert results[0].status == "generated"

        filename, content = await service.download(
            cycle_id=cycle.id,
            org_unit_id=unit.id,
            user=user,
        )
        assert filename.endswith("_budget_template.xlsx")
        assert content.startswith(b"PK")  # .xlsx is a ZIP container
    finally:
        await db_session.execute(delete(ExcelTemplate).where(ExcelTemplate.cycle_id == cycle.id))
        await db_session.execute(delete(BudgetCycle).where(BudgetCycle.id == cycle.id))
        await db_session.execute(delete(OrgUnit).where(OrgUnit.id == unit.id))
        await db_session.execute(delete(AccountCode).where(AccountCode.id == account.id))
        await db_session.execute(delete(User).where(User.id == user.id))
        await db_session.commit()
        get_settings.cache_clear()
