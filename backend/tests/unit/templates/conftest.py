"""Shared fixtures for :mod:`app.domain.templates` unit tests.

The templates service only needs ``execute`` / ``add`` / ``commit`` /
``rollback`` / ``flush`` / ``get`` on the session object. Rather than
ship a full compiled-SQL parser, this ``FakeSession`` stores rows in
typed lists and inspects the compiled statement string for a handful
of easy-to-match substrings. Anything unexpected raises
:class:`AssertionError` so the test surface stays tight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.security.models import OrgUnit, User
from app.core.security.roles import Role
from app.domain.accounts.models import AccountCategory, AccountCode, ActualExpense
from app.domain.audit.actions import AuditAction
from app.domain.cycles.models import BudgetCycle, CycleState
from app.domain.templates.models import ExcelTemplate


def _now() -> datetime:
    """Return a deterministic aware UTC timestamp."""
    return datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc)


@dataclass
class _FakeResult:
    """Minimal :class:`sqlalchemy.Result` stand-in."""

    rows: list[Any] = field(default_factory=list)

    def scalar_one_or_none(self) -> Any:
        """Return the first row (or ``None``) for singleton queries."""
        return self.rows[0] if self.rows else None

    def scalars(self) -> _FakeResult:
        """Return ``self`` — ``.all()`` yields scalar rows."""
        return _FakeResult(rows=list(self.rows))

    def all(self) -> list[Any]:
        """Return every row as a list."""
        return list(self.rows)


class FakeSession:
    """Async-session double tuned to the templates service's SQL shapes.

    The in-memory store holds four row lists — :class:`AccountCode`,
    :class:`ActualExpense`, :class:`ExcelTemplate`, and :class:`OrgUnit`
    — plus a :class:`BudgetCycle` dict keyed by id for :meth:`get`. The
    session intentionally does not implement a join engine; queries are
    matched on substring snippets of the compiled SQL text.
    """

    def __init__(self) -> None:
        """Initialize empty stores + commit counters."""
        self.account_codes: list[AccountCode] = []
        self.actual_expenses: list[ActualExpense] = []
        self.excel_templates: list[ExcelTemplate] = []
        self.org_units: list[OrgUnit] = []
        self.cycles: dict[UUID, BudgetCycle] = {}
        self._pending: list[Any] = []
        self.commits: int = 0
        self.rollbacks: int = 0

    # ------------------------------------------------------------ add/commit
    def add(self, obj: Any) -> None:
        """Queue a row for :meth:`commit`."""
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        self._pending.append(obj)

    async def commit(self) -> None:
        """Materialize pending adds into the matching store list."""
        for obj in self._pending:
            if isinstance(obj, AccountCode):
                self.account_codes.append(obj)
            elif isinstance(obj, ActualExpense):
                self.actual_expenses.append(obj)
            elif isinstance(obj, ExcelTemplate):
                self.excel_templates.append(obj)
            else:  # pragma: no cover — defensive
                raise AssertionError(f"Unexpected add: {type(obj).__name__}")
        self._pending.clear()
        self.commits += 1

    async def rollback(self) -> None:
        """Discard pending adds."""
        self._pending.clear()
        self.rollbacks += 1

    async def flush(self) -> None:
        """Materialize pending adds without bumping the commit counter.

        The production service flushes to obtain ``ExcelTemplate.id``
        before committing. This fake applies pending writes eagerly so
        downstream attribute reads (``template.id``) succeed.
        """
        for obj in self._pending:
            if isinstance(obj, ExcelTemplate):
                self.excel_templates.append(obj)
            elif isinstance(obj, AccountCode):
                self.account_codes.append(obj)
            elif isinstance(obj, ActualExpense):
                self.actual_expenses.append(obj)
        self._pending.clear()

    async def refresh(self, _obj: Any) -> None:
        """No-op refresh — every fake carries the fields the service reads."""
        return None

    async def close(self) -> None:
        """No-op close."""
        return None

    async def get(self, model: Any, pk: Any) -> Any:
        """Route to the in-memory store for ``BudgetCycle`` + ``OrgUnit`` lookups."""
        if model is BudgetCycle:
            return self.cycles.get(pk)
        if model is OrgUnit:
            for unit in self.org_units:
                if unit.id == pk:
                    return unit
            return None
        return None

    # ----------------------------------------------------------------- execute
    async def execute(self, stmt: Any) -> _FakeResult:
        """Dispatch on the compiled statement text."""
        compiled = str(stmt)
        params = _extract_params(stmt)

        # DELETE FROM excel_templates WHERE cycle_id = ? AND org_unit_id = ?
        if compiled.startswith("DELETE FROM excel_templates"):
            cycle_id = params.get("cycle_id_1")
            org_unit_id = params.get("org_unit_id_1")
            self.excel_templates = [
                row
                for row in self.excel_templates
                if not (
                    _coerce_uuid(row.cycle_id) == _coerce_uuid(cycle_id)
                    and _coerce_uuid(row.org_unit_id) == _coerce_uuid(org_unit_id)
                )
            ]
            return _FakeResult(rows=[])

        # SELECT ... FROM account_codes WHERE category = 'operational'
        if "FROM account_codes" in compiled:
            category_filter = params.get("category_1")
            rows = [
                row
                for row in self.account_codes
                if category_filter is None or row.category.value == _enum_value(category_filter)
            ]
            rows.sort(key=lambda r: r.code)
            return _FakeResult(rows=rows)

        # SELECT account_code_id, amount FROM actual_expenses
        # WHERE cycle_id = ? AND org_unit_id = ?
        if "FROM actual_expenses" in compiled:
            cycle_id = params.get("cycle_id_1")
            org_unit_id = params.get("org_unit_id_1")
            rows = [
                (row.account_code_id, row.amount)
                for row in self.actual_expenses
                if _coerce_uuid(row.cycle_id) == _coerce_uuid(cycle_id)
                and _coerce_uuid(row.org_unit_id) == _coerce_uuid(org_unit_id)
            ]
            return _FakeResult(rows=rows)

        # SELECT ... FROM excel_templates WHERE cycle_id = ? AND org_unit_id = ?
        if "FROM excel_templates" in compiled:
            cycle_id = params.get("cycle_id_1")
            org_unit_id = params.get("org_unit_id_1")
            rows = [
                row
                for row in self.excel_templates
                if _coerce_uuid(row.cycle_id) == _coerce_uuid(cycle_id)
                and _coerce_uuid(row.org_unit_id) == _coerce_uuid(org_unit_id)
            ]
            return _FakeResult(rows=rows)

        raise AssertionError(f"Unhandled statement: {compiled}")


def _extract_params(stmt: Any) -> dict[str, Any]:
    """Return the compiled params of ``stmt`` as a plain ``dict``."""
    try:
        compiled = stmt.compile(compile_kwargs={"literal_binds": False})
        return dict(compiled.params)
    except Exception:  # pragma: no cover — defensive
        return {}


def _coerce_uuid(value: Any) -> Any:
    """Normalize a UUID / str / None to a comparable form."""
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):  # pragma: no cover — defensive
        return value


def _enum_value(value: Any) -> str:
    """Return the raw string for an enum or a plain string."""
    return getattr(value, "value", value)


# ----------------------------------------------------------------- model factories
def make_account(
    *,
    code: str,
    name: str = "Operational",
    category: AccountCategory = AccountCategory.operational,
) -> AccountCode:
    """Return a detached :class:`AccountCode` ready for fake seeding."""
    row = AccountCode(
        code=code,
        name=name,
        category=category,
        level=1,
        is_active=True,
    )
    row.id = uuid4()
    return row


def make_org_unit(*, code: str = "4023", name: str = "業務部") -> OrgUnit:
    """Return a detached :class:`OrgUnit` ready for fake seeding."""
    unit = OrgUnit(
        code=code,
        name=name,
        level_code="4023",
        parent_id=None,
        is_filing_unit=True,
        is_reviewer_only=False,
        excluded_for_cycle_ids=[],
    )
    unit.id = uuid4()
    return unit


def make_cycle(*, fiscal_year: int = 2026, currency: str = "TWD") -> BudgetCycle:
    """Return a detached Open :class:`BudgetCycle`."""
    cycle = BudgetCycle(
        fiscal_year=fiscal_year,
        deadline=date(fiscal_year, 12, 31),
        reporting_currency=currency,
        status=CycleState.open.value,
        created_by=uuid4(),
        created_at=_now(),
        updated_at=_now(),
    )
    cycle.id = uuid4()
    cycle.opened_at = _now()
    return cycle


def make_user(*, role: Role = Role.FinanceAdmin) -> User:
    """Return a detached :class:`User` with a single role."""
    user = User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=b"\x00" * 32,
        name="Test",
        email_enc=b"",
        email_hash=b"\x00" * 32,
        roles=[role.value],
        org_unit_id=None,
        is_active=True,
    )
    return user


def make_actual(
    *,
    cycle_id: UUID,
    org_unit_id: UUID,
    account_id: UUID,
    amount: Decimal,
) -> ActualExpense:
    """Return a detached :class:`ActualExpense`."""
    row = ActualExpense(
        cycle_id=cycle_id,
        org_unit_id=org_unit_id,
        account_code_id=account_id,
        amount=amount,
        imported_at=_now(),
        imported_by=uuid4(),
        created_at=_now(),
        updated_at=_now(),
    )
    row.id = uuid4()
    return row


class FakeAudit:
    """In-memory :class:`AuditService` stand-in."""

    def __init__(self) -> None:
        """Initialize an empty event log."""
        self.events: list[dict[str, Any]] = []

    async def record(
        self,
        *,
        action: AuditAction,
        resource_type: str,
        resource_id: UUID | None = None,
        user_id: UUID | None = None,
        ip_address: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Capture the call without touching a DB."""
        self.events.append(
            {
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "user_id": user_id,
                "ip_address": ip_address,
                "details": dict(details) if details else {},
            }
        )


@pytest.fixture
def fake_session() -> FakeSession:
    """Return a fresh in-memory :class:`FakeSession`."""
    return FakeSession()
