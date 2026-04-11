"""Unit tests for :mod:`app.domain.accounts.service.AccountService`."""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from app.core.errors import BatchValidationError, NotFoundError
from app.domain.accounts.models import AccountCategory
from app.domain.accounts.service import AccountCodeWrite
from app.domain.audit.actions import AuditAction
from tests.unit.accounts.conftest import FakeSession, make_account_code


# -------------------------------------------------------------------- list
async def test_list_returns_all_codes(
    account_service: Any,
    fake_session: FakeSession,
) -> None:
    """``list()`` without filter returns every seeded code."""
    fake_session.account_codes = [
        make_account_code(code="5101", category=AccountCategory.operational),
        make_account_code(code="5102", category=AccountCategory.operational),
        make_account_code(code="6001", category=AccountCategory.personnel),
    ]
    result = await account_service.list()
    codes = {r.code for r in result}
    assert codes == {"5101", "5102", "6001"}


async def test_list_filtered_by_category(
    account_service: Any,
    fake_session: FakeSession,
) -> None:
    """Passing a category narrows the result set."""
    fake_session.account_codes = [
        make_account_code(code="5101", category=AccountCategory.operational),
        make_account_code(code="5102", category=AccountCategory.operational),
        make_account_code(code="6001", category=AccountCategory.personnel),
    ]
    result = await account_service.list(category=AccountCategory.operational)
    codes = {r.code for r in result}
    assert codes == {"5101", "5102"}


# ---------------------------------------------------------------- upsert
async def test_upsert_creates_new_code(
    account_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """Upserting a fresh code inserts a row and audits ACCOUNT_CREATE."""
    body = AccountCodeWrite(
        code="5101",
        name="Office supplies",
        category=AccountCategory.operational,
        level=1,
    )
    row = await account_service.upsert(data=body, user=system_admin)
    assert row.code == "5101"
    assert len(fake_session.account_codes) == 1
    events = account_service._audit.events
    assert len(events) == 1
    assert events[0]["action"] is AuditAction.ACCOUNT_CREATE
    assert events[0]["details"]["code"] == "5101"


async def test_upsert_updates_existing_code(
    account_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """A second upsert with the same code updates the row and audits UPDATE."""
    fake_session.account_codes = [make_account_code(code="5101", name="Old name")]
    body = AccountCodeWrite(
        code="5101",
        name="New name",
        category=AccountCategory.operational,
        level=2,
    )
    row = await account_service.upsert(data=body, user=system_admin)
    assert row.name == "New name"
    assert row.level == 2
    assert len(fake_session.account_codes) == 1
    events = account_service._audit.events
    assert events[0]["action"] is AuditAction.ACCOUNT_UPDATE


# ----------------------------------------------------------- get_by_code
async def test_get_by_code_not_found_raises_account_001(
    account_service: Any,
) -> None:
    """``get_by_code`` on a missing code raises NotFoundError(ACCOUNT_001)."""
    with pytest.raises(NotFoundError) as exc_info:
        await account_service.get_by_code("missing")
    assert exc_info.value.code == "ACCOUNT_001"


async def test_get_by_code_returns_row(
    account_service: Any,
    fake_session: FakeSession,
) -> None:
    """A known code returns the matching ORM row."""
    fake_session.account_codes = [
        make_account_code(code="5101"),
    ]
    row = await account_service.get_by_code("5101")
    assert row.code == "5101"


# ---------------------------------------------- category accessor methods
async def test_get_operational_codes_set(
    account_service: Any,
    fake_session: FakeSession,
) -> None:
    """Only operational codes come back."""
    fake_session.account_codes = [
        make_account_code(code="5101", category=AccountCategory.operational),
        make_account_code(code="5102", category=AccountCategory.operational),
        make_account_code(code="6001", category=AccountCategory.personnel),
    ]
    result = await account_service.get_operational_codes_set()
    assert result == {"5101", "5102"}


async def test_get_codes_by_category_personnel(
    account_service: Any,
    fake_session: FakeSession,
) -> None:
    """``get_codes_by_category(personnel)`` returns personnel codes only."""
    fake_session.account_codes = [
        make_account_code(code="5101", category=AccountCategory.operational),
        make_account_code(code="6001", category=AccountCategory.personnel),
        make_account_code(code="6002", category=AccountCategory.personnel),
    ]
    result = await account_service.get_codes_by_category(AccountCategory.personnel)
    assert result == {"6001", "6002"}


# ------------------------------------------------------------ import_actuals
def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Return a CSV payload for the actuals importer with a stable header order."""
    buf = io.StringIO()
    headers = ["org_unit_code", "account_code", "amount"]
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


async def test_import_actuals_happy_path(
    account_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """Valid CSV imports every row and emits an ACTUALS_IMPORT audit entry."""
    fake_session.account_codes = [
        make_account_code(code="5101", category=AccountCategory.operational),
    ]
    cycle_id = uuid4()
    content = _csv_bytes(
        [
            {"org_unit_code": "4000", "account_code": "5101", "amount": "100"},
            {"org_unit_code": "4023", "account_code": "5101", "amount": "200"},
        ]
    )
    summary = await account_service.import_actuals(
        cycle_id=cycle_id,
        filename="actuals.csv",
        content=content,
        user=system_admin,
    )
    assert summary.rows_imported == 2
    assert summary.org_units_affected == ["4000", "4023"]
    assert len(fake_session.actual_expenses) == 2
    assert all(
        r.amount == Decimal("100.00") or r.amount == Decimal("200.00")
        for r in fake_session.actual_expenses
    )
    events = account_service._audit.events
    assert events[0]["action"] is AuditAction.ACTUALS_IMPORT


async def test_import_actuals_invalid_row_raises_and_persists_nothing(
    account_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """On any row failure: raise ACCOUNT_002 and keep the store untouched (CR-004)."""
    fake_session.account_codes = [
        make_account_code(code="5101", category=AccountCategory.operational),
    ]
    cycle_id = uuid4()
    content = _csv_bytes(
        [
            {"org_unit_code": "4000", "account_code": "5101", "amount": "100"},
            {"org_unit_code": "9999", "account_code": "5101", "amount": "200"},
        ]
    )
    with pytest.raises(BatchValidationError) as exc_info:
        await account_service.import_actuals(
            cycle_id=cycle_id,
            filename="actuals.csv",
            content=content,
            user=system_admin,
        )
    assert exc_info.value.code == "ACCOUNT_002"
    # CR-004 — zero rows persisted on failure.
    assert fake_session.actual_expenses == []
    # No ACTUALS_IMPORT audit.
    assert all(e["action"] is not AuditAction.ACTUALS_IMPORT for e in account_service._audit.events)


async def test_import_actuals_empty_file_raises(
    account_service: Any,
    fake_session: FakeSession,
    system_admin: Any,
) -> None:
    """An empty parsed file triggers a batch-level ACCOUNT_002 error."""
    fake_session.account_codes = [
        make_account_code(code="5101", category=AccountCategory.operational),
    ]
    cycle_id = uuid4()
    content = b"org_unit_code,account_code,amount\n"
    with pytest.raises(BatchValidationError) as exc_info:
        await account_service.import_actuals(
            cycle_id=cycle_id,
            filename="actuals.csv",
            content=content,
            user=system_admin,
        )
    assert exc_info.value.code == "ACCOUNT_002"


async def test_import_actuals_closed_cycle_raises_cycle_004(
    account_service: Any,
    system_admin: Any,
) -> None:
    """Closed cycle → raises CYCLE_004 before any file parsing (Batch 4)."""
    from app.core.errors import AppError

    class _ClosedAsserter:
        async def assert_open(self, cycle_id: Any) -> None:
            raise AppError("CYCLE_004", f"Cycle {cycle_id} is not open")

    cycle_id = uuid4()
    with pytest.raises(AppError) as exc_info:
        await account_service.import_actuals(
            cycle_id=cycle_id,
            filename="actuals.csv",
            content=b"org_unit_code,account_code,amount\n",
            user=system_admin,
            cycle_service=_ClosedAsserter(),
        )
    assert exc_info.value.code == "CYCLE_004"
