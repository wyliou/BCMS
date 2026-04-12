"""Integration smoke test for :class:`PersonnelImportService` (FR-024..FR-026).

Requires a live Postgres backend — skipped when none is reachable via
``BC_DATABASE_URL``. Verifies the real ORM round-trip for the personnel
import pipeline against a ``tmp_path``-rooted storage directory.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.clock import now_utc
from app.core.security.models import OrgUnit, User
from app.core.security.roles import Role
from app.domain.accounts.models import AccountCategory, AccountCode
from app.domain.cycles.models import BudgetCycle, CycleState
from app.domain.personnel.models import PersonnelBudgetLine, PersonnelBudgetUpload
from app.domain.personnel.service import PersonnelImportService
from tests.integration.conftest import skip_unless_postgres

pytestmark = [pytest.mark.integration, skip_unless_postgres]


def _make_csv(rows: list[tuple[str, str, int | str]]) -> bytes:
    """Build a minimal valid personnel CSV.

    Args:
        rows: ``(dept_id, account_code, amount)`` tuples.

    Returns:
        bytes: Raw UTF-8 CSV content.
    """
    lines = ["dept_id,account_code,amount"]
    for dept_id, account_code, amount in rows:
        lines.append(f"{dept_id},{account_code},{amount}")
    return "\n".join(lines).encode("utf-8")


async def _seed_basic(
    db: AsyncSession,
) -> tuple[BudgetCycle, OrgUnit, User, list[AccountCode]]:
    """Insert a minimal cycle + unit + user + personnel accounts.

    Args:
        db: Active async session.

    Returns:
        tuple: ``(cycle, unit, user, accounts)`` with unique ids.
    """
    now = now_utc()
    user = User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=uuid4().bytes.ljust(32, b"\x00"),
        name="HR Upload Tester",
        email_enc=b"hr@example.com",
        email_hash=uuid4().bytes.ljust(32, b"\x00"),
        roles=[Role.HRAdmin.value],
        org_unit_id=None,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    await db.flush()

    unit = OrgUnit(
        id=uuid4(),
        code=f"T{uuid4().hex[:4].upper()}",
        name="Test HR Unit",
        level_code="4023",
        parent_id=None,
        is_filing_unit=True,
        is_reviewer_only=False,
        excluded_for_cycle_ids=[],
    )
    db.add(unit)
    await db.flush()

    user.org_unit_id = unit.id
    await db.flush()

    cycle = BudgetCycle(
        id=uuid4(),
        fiscal_year=2090,  # far future to avoid year conflicts
        deadline=date(2090, 12, 31),
        reporting_currency="TWD",
        status=CycleState.open.value,
        created_by=user.id,
        created_at=now,
        updated_at=now,
        opened_at=now,
    )
    db.add(cycle)
    await db.flush()

    accounts: list[AccountCode] = []
    for i in range(3):
        code = f"PERS{uuid4().hex[:4].upper()}"
        acct = AccountCode(
            id=uuid4(),
            code=code,
            name=f"Personnel Account {i}",
            category=AccountCategory.personnel,
            level=1,
            is_active=True,
        )
        db.add(acct)
        accounts.append(acct)
    await db.flush()

    return cycle, unit, user, accounts


@pytest.mark.asyncio
async def test_integration_full_round_trip(db: AsyncSession, tmp_path: Path) -> None:
    """Valid CSV → version=1, uploads + lines persisted to Postgres."""
    settings = get_settings()
    # Point storage at a temp dir so no real filesystem is needed.
    original_root = settings.storage_root
    settings.storage_root = str(tmp_path)

    try:
        cycle, unit, user, accounts = await _seed_basic(db)
        content = _make_csv(
            rows=[
                (unit.code, accounts[0].code, 1000),
                (unit.code, accounts[1].code, 2000),
            ]
        )
        service = PersonnelImportService(db)
        upload = await service.import_(
            cycle_id=cycle.id,
            filename="hr_import.csv",
            content=content,
            user=user,
        )

        assert upload.id is not None
        assert upload.version == 1
        assert upload.cycle_id == cycle.id

        # Verify lines were persisted.
        lines_result = await db.execute(
            select(PersonnelBudgetLine).where(PersonnelBudgetLine.upload_id == upload.id)
        )
        lines = list(lines_result.scalars().all())
        assert len(lines) == 2

    finally:
        settings.storage_root = original_root
        # Teardown: delete inserted rows in reverse FK order.
        await db.execute(
            delete(PersonnelBudgetLine).where(
                PersonnelBudgetLine.upload_id.in_(
                    select(PersonnelBudgetUpload.id).where(
                        PersonnelBudgetUpload.cycle_id == cycle.id
                    )
                )
            )
        )
        await db.execute(
            delete(PersonnelBudgetUpload).where(PersonnelBudgetUpload.cycle_id == cycle.id)
        )
        await db.commit()
