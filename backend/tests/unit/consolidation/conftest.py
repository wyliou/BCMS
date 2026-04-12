"""Shared fixtures for :mod:`app.domain.consolidation` unit tests.

The consolidation services issue a relatively complex set of SQL
statements touching the budget / personnel / shared cost / actuals /
templates / org_units / resubmit tables. Rather than re-implementing
the FakeSession SQL dispatcher for all of those shapes, the fixtures
here provide a narrow :class:`StubSession` that supports only
``get``/``execute``/``commit``/``rollback`` plus a simple dispatcher
keyed on the ORM class.

Most tests override the service's private fetch helpers directly via
``monkeypatch.setattr`` — that keeps the SQL shape details out of the
test assertions and focuses each test on the business rule under
scrutiny.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.security.models import OrgUnit, User
from app.core.security.roles import Role
from app.domain.accounts.models import AccountCategory, AccountCode
from app.domain.budget_uploads.models import BudgetUpload
from app.domain.cycles.models import BudgetCycle, CycleState
from app.domain.notifications.models import ResubmitRequest
from app.domain.personnel.models import PersonnelBudgetUpload
from app.domain.shared_costs.models import SharedCostUpload
from app.domain.templates.models import ExcelTemplate


def _now() -> datetime:
    """Return a deterministic aware UTC timestamp."""
    return datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc)


class _Result:
    """Minimal :class:`sqlalchemy.Result` stand-in."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        """Initialize with the row list."""
        self._rows = rows or []

    def scalars(self) -> _Result:
        """Return ``self`` — ``.all()`` yields the rows."""
        return self

    def scalar_one_or_none(self) -> Any:
        """Return the first row or ``None``."""
        return self._rows[0] if self._rows else None

    def first(self) -> Any:
        """Return the first row or ``None``."""
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        """Return a copy of the row list."""
        return list(self._rows)


class StubSession:
    """Stub :class:`AsyncSession` that stores rows keyed on ORM class.

    Tests populate ``session.store[ModelClass]`` directly. The
    :meth:`get` method uses those stores; :meth:`execute` raises
    :class:`AssertionError` if a test forgets to override an internal
    fetcher (so the override pattern is enforced).
    """

    def __init__(self) -> None:
        """Initialize with empty stores."""
        self.store: dict[type, list[Any]] = {}
        self._cycles: dict[UUID, BudgetCycle] = {}
        self._users: dict[UUID, User] = {}
        self.commits = 0
        self.rollbacks = 0

    def register_cycle(self, cycle: BudgetCycle) -> None:
        """Insert ``cycle`` into the cycle store keyed by id."""
        self._cycles[cycle.id] = cycle

    def register_user(self, user: User) -> None:
        """Insert ``user`` into the user store keyed by id."""
        self._users[user.id] = user

    async def get(self, model: type, pk: Any) -> Any:
        """Route :meth:`AsyncSession.get` to the matching store."""
        if model is BudgetCycle:
            return self._cycles.get(pk)
        if model is User:
            return self._users.get(pk)
        for row in self.store.get(model, []):
            if getattr(row, "id", None) == pk:
                return row
        return None

    async def execute(self, _stmt: Any) -> _Result:
        """Raise — tests must override fetchers before invoking the service."""
        raise AssertionError(
            "StubSession.execute should not be called — override the service's "
            "private fetch helpers in your test."
        )

    async def commit(self) -> None:
        """Increment commit counter."""
        self.commits += 1

    async def rollback(self) -> None:
        """Increment rollback counter."""
        self.rollbacks += 1

    async def close(self) -> None:
        """No-op close."""
        return None

    def add(self, _obj: Any) -> None:
        """No-op add."""
        return None

    async def flush(self) -> None:
        """No-op flush."""
        return None


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------
def make_cycle(
    *,
    fiscal_year: int = 2026,
    state: CycleState = CycleState.open,
    reporting_currency: str = "TWD",
) -> BudgetCycle:
    """Return a detached :class:`BudgetCycle`."""
    cycle = BudgetCycle(
        fiscal_year=fiscal_year,
        deadline=date(fiscal_year, 12, 31),
        reporting_currency=reporting_currency,
        status=state.value,
        created_by=uuid4(),
        created_at=_now(),
        updated_at=_now(),
    )
    cycle.id = uuid4()
    cycle.opened_at = _now() if state == CycleState.open else None
    cycle.closed_at = None
    return cycle


def make_org_unit(
    *,
    code: str = "4023",
    name: str | None = None,
    level_code: str = "4000",
    is_filing_unit: bool = True,
) -> OrgUnit:
    """Return a detached :class:`OrgUnit`."""
    unit = OrgUnit(
        code=code,
        name=name or code,
        level_code=level_code,
        parent_id=None,
        is_filing_unit=is_filing_unit,
        is_reviewer_only=False,
        excluded_for_cycle_ids=[],
    )
    unit.id = uuid4()
    return unit


def make_account(
    *,
    code: str = "51010000",
    name: str = "Operational",
    category: AccountCategory = AccountCategory.operational,
) -> AccountCode:
    """Return a detached :class:`AccountCode`."""
    row = AccountCode(
        code=code,
        name=name,
        category=category,
        level=1,
        is_active=True,
    )
    row.id = uuid4()
    return row


def make_user(
    *,
    role: Role = Role.SystemAdmin,
    org_unit_id: UUID | None = None,
    email: str = "tester@example.com",
    additional_roles: list[Role] | None = None,
) -> User:
    """Return a detached :class:`User`."""
    roles = [role.value]
    if additional_roles:
        roles.extend(r.value for r in additional_roles)
    user = User(
        sso_id_enc=b"",
        sso_id_hash=b"\x00" * 32,
        name="Tester",
        email_enc=email.encode("utf-8"),
        email_hash=b"\x00" * 32,
        roles=roles,
        org_unit_id=org_unit_id,
        is_active=True,
    )
    user.id = uuid4()
    return user


def make_budget_upload(
    *,
    cycle_id: UUID,
    org_unit_id: UUID,
    version: int = 1,
    uploaded_at: datetime | None = None,
) -> BudgetUpload:
    """Return a detached :class:`BudgetUpload`."""
    row = BudgetUpload(
        cycle_id=cycle_id,
        org_unit_id=org_unit_id,
        uploader_id=uuid4(),
        version=version,
        file_path_enc=b"\x00",
        file_hash=b"\x00" * 32,
        file_size_bytes=100,
        row_count=1,
        status="valid",
        uploaded_at=uploaded_at or _now(),
    )
    row.id = uuid4()
    return row


def make_template(
    *,
    cycle_id: UUID,
    org_unit_id: UUID,
    download_count: int = 0,
    generation_error: str | None = None,
) -> ExcelTemplate:
    """Return a detached :class:`ExcelTemplate` row."""
    row = ExcelTemplate(
        cycle_id=cycle_id,
        org_unit_id=org_unit_id,
        file_path_enc=b"\x00",
        file_hash=b"\x00" * 32,
        generated_at=_now(),
        generated_by=uuid4(),
        download_count=download_count,
        generation_error=generation_error,
    )
    row.id = uuid4()
    return row


def make_resubmit(
    *,
    cycle_id: UUID,
    org_unit_id: UUID,
) -> ResubmitRequest:
    """Return a detached :class:`ResubmitRequest`."""
    row = ResubmitRequest(
        cycle_id=cycle_id,
        org_unit_id=org_unit_id,
        requester_id=uuid4(),
        target_version=None,
        reason="please fix",
        requested_at=_now(),
    )
    row.id = uuid4()
    return row


def make_personnel_upload(
    *,
    cycle_id: UUID,
    version: int = 1,
) -> PersonnelBudgetUpload:
    """Return a detached :class:`PersonnelBudgetUpload`."""
    row = PersonnelBudgetUpload(
        cycle_id=cycle_id,
        uploader_user_id=uuid4(),
        uploaded_at=_now(),
        filename="p.csv",
        file_hash="0" * 64,
        version=version,
        affected_org_units_summary={"unit_count": 0, "unit_codes": []},
    )
    row.id = uuid4()
    return row


def make_shared_cost_upload(
    *,
    cycle_id: UUID,
    version: int = 1,
) -> SharedCostUpload:
    """Return a detached :class:`SharedCostUpload`."""
    row = SharedCostUpload(
        cycle_id=cycle_id,
        uploader_user_id=uuid4(),
        uploaded_at=_now(),
        filename="s.csv",
        file_hash=b"\x00" * 32,
        version=version,
        affected_org_units_summary={"unit_count": 0, "unit_codes": []},
    )
    row.id = uuid4()
    return row


@pytest.fixture
def stub_session() -> StubSession:
    """Return a fresh :class:`StubSession`."""
    return StubSession()


__all__ = [
    "Decimal",
    "StubSession",
    "make_account",
    "make_budget_upload",
    "make_cycle",
    "make_org_unit",
    "make_personnel_upload",
    "make_resubmit",
    "make_shared_cost_upload",
    "make_template",
    "make_user",
]
