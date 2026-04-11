"""Shared fixtures for :mod:`app.domain.cycles` unit tests.

The :class:`FakeSession` double is intentionally narrow: the cycles
service only needs ``execute`` / ``add`` / ``commit`` / ``flush`` / ``get``
/ ``rollback`` / ``close`` plus :meth:`delete` routed through
``execute``. Everything else raises :class:`AssertionError` so the test
surface stays tight.

The session recognises four table shapes:

* ``budget_cycles`` — CRUD via service methods.
* ``cycle_reminder_schedules`` — insert / delete / select.
* ``org_units`` — read-only list for the filing-unit enumeration.
* ``users`` — read-only list for the manager check.

Every query is parsed from the compiled statement text; the compiled
output is stable enough for the few SQL shapes the service issues.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.core.security.models import OrgUnit, User
from app.core.security.roles import Role
from app.domain.audit.actions import AuditAction
from app.domain.cycles.models import BudgetCycle, CycleReminderSchedule, CycleState


# --------------------------------------------------------------------- helpers
def _now() -> datetime:
    """Return a deterministic aware UTC timestamp."""
    return datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc)


@dataclass
class _FakeResult:
    """Minimal :class:`sqlalchemy.Result` stand-in."""

    rows: list[Any] = field(default_factory=list)

    def scalar_one_or_none(self) -> Any:
        """Return the first row (or ``None``)."""
        return self.rows[0] if self.rows else None

    def scalars(self) -> _FakeResult:
        """Return ``self`` — ``.all()`` returns scalar rows."""
        return _FakeResult(rows=list(self.rows))

    def first(self) -> Any:
        """Return the first row or ``None``."""
        return self.rows[0] if self.rows else None

    def all(self) -> list[Any]:
        """Return all rows."""
        return list(self.rows)


class FakeSession:
    """Narrow :class:`AsyncSession` stand-in for cycles unit tests."""

    def __init__(self) -> None:
        """Initialize the stores."""
        self.cycles: list[BudgetCycle] = []
        self.reminders: list[CycleReminderSchedule] = []
        self.org_units: list[OrgUnit] = []
        self.users: list[User] = []
        self.commits: int = 0
        self.rollbacks: int = 0
        self._pending: list[Any] = []

    # ----------------------------------------------------------- ORM surface
    def add(self, obj: Any) -> None:
        """Queue ``obj`` for insert on the next commit."""
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        self._pending.append(obj)

    async def flush(self) -> None:
        """Flush — immediately materialize pending adds into the stores."""
        for obj in list(self._pending):
            self._store(obj)
        self._pending.clear()

    async def commit(self) -> None:
        """Commit — flush any pending adds."""
        await self.flush()
        self.commits += 1

    async def rollback(self) -> None:
        """Drop pending adds."""
        self._pending.clear()
        self.rollbacks += 1

    async def refresh(self, _obj: Any) -> None:
        """No-op refresh — fakes carry their defaults."""
        return None

    async def close(self) -> None:
        """No-op close."""
        return None

    async def get(self, model: type, pk: Any) -> Any:
        """Emulate :meth:`AsyncSession.get` for the cycles + org_units stores."""
        if model is BudgetCycle:
            for row in self.cycles:
                if row.id == pk:
                    return row
            return None
        if model is OrgUnit:
            for row in self.org_units:
                if row.id == pk:
                    return row
            return None
        raise AssertionError(f"Unsupported model in FakeSession.get: {model!r}")

    # ------------------------------------------------------------- routing
    def _store(self, obj: Any) -> None:
        """Route an inserted object to the appropriate backing list."""
        if isinstance(obj, BudgetCycle):
            # Replace row with same id if already present (for updates).
            for i, existing in enumerate(self.cycles):
                if existing.id == obj.id:
                    self.cycles[i] = obj
                    return
            self.cycles.append(obj)
        elif isinstance(obj, CycleReminderSchedule):
            self.reminders.append(obj)
        else:  # pragma: no cover — defensive
            raise AssertionError(f"Unexpected ORM add type: {type(obj).__name__}")

    async def execute(self, stmt: Any, params: Any | None = None) -> _FakeResult:
        """Route a compiled SQL statement to the in-memory store."""
        del params
        compiled = str(stmt)

        # --- DELETE ----------------------------------------------------
        if compiled.startswith("DELETE FROM cycle_reminder_schedules"):
            cycle_id = _extract_uuid(stmt, "cycle_id")
            self.reminders = [r for r in self.reminders if r.cycle_id != cycle_id]
            return _FakeResult(rows=[])

        # --- SELECT budget_cycles --------------------------------------
        if "FROM budget_cycles" in compiled:
            rows = list(self.cycles)
            params_dict = _params(stmt)
            fy = params_dict.get("fiscal_year_1")
            if fy is not None:
                rows = [r for r in rows if r.fiscal_year == fy]
            status_val = params_dict.get("status_1")
            if status_val is not None and "budget_cycles.status !=" in compiled:
                rows = [r for r in rows if r.status != status_val]
            elif status_val is not None and "budget_cycles.status =" in compiled:
                rows = [r for r in rows if r.status == status_val]
            rows.sort(key=lambda r: (r.fiscal_year, r.created_at), reverse=True)
            return _FakeResult(rows=rows)

        # --- SELECT cycle_reminder_schedules ---------------------------
        if "FROM cycle_reminder_schedules" in compiled:
            cycle_id = _extract_uuid(stmt, "cycle_id")
            rows = [r for r in self.reminders if cycle_id is None or r.cycle_id == cycle_id]
            return _FakeResult(rows=rows)

        # --- SELECT org_units ------------------------------------------
        if "FROM org_units" in compiled:
            rows = list(self.org_units)
            params_dict = _params(stmt)
            fu_is = "org_units.is_filing_unit IS" in compiled
            fu_eq = "org_units.is_filing_unit = 1" in compiled
            if fu_is or fu_eq:
                rows = [r for r in rows if r.is_filing_unit]
            level_val = params_dict.get("level_code_1")
            if level_val is not None and "org_units.level_code !=" in compiled:
                rows = [r for r in rows if r.level_code != level_val]
            # IN clause for id
            id_in = _collect_in_values(params_dict, "id_")
            if id_in and "org_units.id IN" in compiled:
                rows = [r for r in rows if r.id in id_in]
            rows.sort(key=lambda r: r.code)
            return _FakeResult(rows=rows)

        # --- SELECT users ----------------------------------------------
        if "FROM users" in compiled:
            rows = list(self.users)
            params_dict = _params(stmt)
            # Filter: is_active is true
            if "users.is_active IS" in compiled or "users.is_active = 1" in compiled:
                rows = [r for r in rows if r.is_active]
            ou_in = _collect_in_values(params_dict, "org_unit_id_")
            if ou_in and "users.org_unit_id IN" in compiled:
                rows = [r for r in rows if r.org_unit_id in ou_in]
            return _FakeResult(rows=rows)

        raise AssertionError(f"Unhandled statement in FakeSession: {compiled}")


def _params(stmt: Any) -> dict[str, Any]:
    """Return the compiled statement's bound parameters."""
    try:
        compiled = stmt.compile(compile_kwargs={"literal_binds": False})
        return dict(compiled.params)
    except Exception:  # pragma: no cover — defensive
        return {}


def _extract_uuid(stmt: Any, param_name: str) -> UUID | None:
    """Pull the named ``cycle_id`` parameter out of the statement."""
    params = _params(stmt)
    for key, value in params.items():
        if key.startswith(param_name):
            if isinstance(value, UUID):
                return value
            try:
                return UUID(str(value))
            except (ValueError, TypeError):
                continue
    return None


def _collect_in_values(params: dict[str, Any], prefix: str) -> set[Any]:
    """Return a set of bound parameter values whose key starts with ``prefix``."""
    collected: set[Any] = set()
    for key, value in params.items():
        if not key.startswith(prefix):
            continue
        if isinstance(value, (list, tuple, set, frozenset)):
            collected.update(value)
        else:
            collected.add(value)
    return collected


# --------------------------------------------------------------------- builders
def make_org_unit(
    *,
    code: str,
    name: str | None = None,
    level_code: str = "4000",
    is_filing_unit: bool = True,
    parent_id: UUID | None = None,
    excluded_for_cycle_ids: list[str] | None = None,
) -> OrgUnit:
    """Construct a detached :class:`OrgUnit` for test seeding."""
    row = OrgUnit(
        code=code,
        name=name or code,
        level_code=level_code,
        parent_id=parent_id,
        is_filing_unit=is_filing_unit,
        is_reviewer_only=False,
        excluded_for_cycle_ids=list(excluded_for_cycle_ids or []),
        created_at=_now(),
        updated_at=_now(),
    )
    row.id = uuid4()
    return row


def make_user(
    *,
    roles: list[Role],
    org_unit_id: UUID | None,
    email: str = "user@example.invalid",
    is_active: bool = True,
) -> User:
    """Construct a detached :class:`User` for test seeding."""
    user = User(
        sso_id_enc=b"sso",
        sso_id_hash=b"\x00" * 32,
        name="Test User",
        email_enc=email.encode("utf-8"),
        email_hash=b"\x01" * 32,
        roles=[r.value for r in roles],
        org_unit_id=org_unit_id,
        is_active=is_active,
        created_at=_now(),
        updated_at=_now(),
    )
    user.id = uuid4()
    return user


def make_system_admin() -> User:
    """Return a detached SystemAdmin :class:`User`."""
    return make_user(roles=[Role.SystemAdmin], org_unit_id=None)


def make_finance_admin() -> User:
    """Return a detached FinanceAdmin :class:`User`."""
    return make_user(roles=[Role.FinanceAdmin], org_unit_id=None)


def make_cycle(
    *,
    fiscal_year: int = 2026,
    status: CycleState = CycleState.draft,
    deadline: date | None = None,
    closed_at: datetime | None = None,
) -> BudgetCycle:
    """Construct a detached :class:`BudgetCycle` for seeding."""
    row = BudgetCycle(
        fiscal_year=fiscal_year,
        deadline=deadline or date(2026, 12, 31),
        reporting_currency="TWD",
        status=status.value,
        closed_at=closed_at,
        created_by=uuid4(),
        created_at=_now(),
        updated_at=_now(),
    )
    row.id = uuid4()
    return row


# --------------------------------------------------------------------- fixtures
@pytest.fixture
def fake_session() -> FakeSession:
    """Return a fresh in-memory :class:`FakeSession`."""
    return FakeSession()


@pytest.fixture
def system_admin() -> User:
    """Return a detached SystemAdmin user."""
    return make_system_admin()


class FakeAudit:
    """In-memory stand-in for :class:`AuditService`."""

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
        """Record a call."""
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


@pytest_asyncio.fixture
async def cycle_service(
    fake_session: FakeSession,
) -> AsyncIterator[Any]:
    """Yield a :class:`CycleService` wired to the fake session + fake audit."""
    from app.domain.cycles.service import CycleService

    service = CycleService(fake_session)  # type: ignore[arg-type]
    service._audit = FakeAudit()  # type: ignore[assignment]
    yield service
