"""Integration smoke test for :class:`BudgetUploadService`.

Requires a live Postgres backend — skipped when none is reachable via
``BC_DATABASE_URL``. Verifies the real ORM round-trip for the upload
pipeline against a ``tmp_path``-rooted storage directory.
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
from app.domain.budget_uploads.models import BudgetLine, BudgetUpload
from app.domain.budget_uploads.service import BudgetUploadService
from app.domain.cycles.models import BudgetCycle, CycleState
from tests.integration.conftest import skip_unless_postgres
from tests.unit.budget_uploads.conftest import build_valid_workbook

pytestmark = [pytest.mark.integration, skip_unless_postgres]


async def _seed_basic(db: AsyncSession) -> tuple[BudgetCycle, OrgUnit, User, list[AccountCode]]:
    """Insert a minimal cycle + unit + user + operational accounts.

    Args:
        db: Active async session.

    Returns:
        tuple: ``(cycle, unit, user, accounts)`` with unique ids to
        avoid collisions with other integration tests.
    """
    now = now_utc()
    user = User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=uuid4().bytes.ljust(32, b"\x00"),
        name="Budget Upload Tester",
        email_enc=b"tester@example.com",
        email_hash=uuid4().bytes.ljust(32, b"\x00"),
        roles=[Role.FilingUnitManager.value],
        org_unit_id=None,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    await db.flush()

    unit = OrgUnit(
        id=uuid4(),
        code=f"BU{uuid4().hex[:4]}",
        name="Budget Filing Unit",
        level_code="4023",
        parent_id=None,
        is_filing_unit=True,
        is_reviewer_only=False,
        excluded_for_cycle_ids=[],
        created_at=now,
        updated_at=now,
    )
    db.add(unit)
    user.org_unit_id = unit.id
    await db.flush()

    cycle = BudgetCycle(
        id=uuid4(),
        fiscal_year=2099,
        deadline=date(2099, 12, 31),
        reporting_currency="TWD",
        status=CycleState.open.value,
        created_by=user.id,
        created_at=now,
        updated_at=now,
        opened_at=now,
    )
    db.add(cycle)

    accounts: list[AccountCode] = []
    for code in ("5101", "5102"):
        row = AccountCode(
            code=f"{code}-{uuid4().hex[:4]}",
            name=f"Account {code}",
            category=AccountCategory.operational,
            level=1,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        accounts.append(row)
    await db.commit()
    return cycle, unit, user, accounts


async def test_upload_round_trip(db_session: AsyncSession, tmp_path: Path) -> None:
    """Persist an upload end-to-end and verify lines + version round-trip."""
    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(get_settings(), "storage_root", str(tmp_path), raising=False)
        cycle, unit, user, accounts = await _seed_basic(db_session)

        service = BudgetUploadService(db_session)
        content = build_valid_workbook(
            dept_code=unit.code,
            rows=[(accounts[0].code, accounts[0].name, "0", 500)],
        )
        upload = await service.upload(
            cycle_id=cycle.id,
            org_unit_id=unit.id,
            filename="integration.xlsx",
            content=content,
            user=user,
        )

        assert upload.version == 1
        assert upload.row_count == 1

        lines = list(
            (await db_session.execute(select(BudgetLine).where(BudgetLine.upload_id == upload.id)))
            .scalars()
            .all()
        )
        assert len(lines) == 1
        assert lines[0].amount == 500

        # Cleanup so subsequent runs don't collide.
        await db_session.execute(delete(BudgetLine).where(BudgetLine.upload_id == upload.id))
        await db_session.execute(delete(BudgetUpload).where(BudgetUpload.id == upload.id))
        await db_session.commit()
    finally:
        monkey.undo()
