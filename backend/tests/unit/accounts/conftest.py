"""Shared fixtures for :mod:`app.domain.accounts` unit tests.

Like the audit / notifications unit tiers, these tests run against an
in-memory session double rather than Postgres. The :class:`FakeSession`
class implements just enough of the :class:`AsyncSession` surface to
drive :class:`app.domain.accounts.service.AccountService`:

* ``execute(stmt)`` — routed by inspecting the compiled SQL text so the
  real ORM statements from the service exercise the fake store.
* ``add(obj)`` — queues a row for the pending insert set.
* ``commit()``/``rollback()`` — flush the pending queue into the store.
* ``refresh(obj)`` — no-op.
* ``delete(stmt)`` path via ``execute`` — removes rows matching the
  compiled ``WHERE`` clause.

Real Postgres round-trips live in
``tests/integration/accounts/test_accounts_integration.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.core.security.models import User
from app.core.security.roles import Role
from app.domain.accounts.models import AccountCategory, AccountCode, ActualExpense
from app.domain.audit.actions import AuditAction


class _FakeResult:
    """Minimal :class:`sqlalchemy.Result` stand-in.

    Supports the three accessor shapes the service uses:
    :meth:`scalar_one_or_none`, :meth:`scalars` with ``.all()``, and
    :meth:`all` returning tuples.
    """

    def __init__(self, rows: list[Any], *, scalar_mode: bool = False) -> None:
        """Store rows + whether the caller expects scalar values.

        Args:
            rows: The underlying iterable.
            scalar_mode: When ``True``, ``all()`` returns the rows as-is
                (tuples); when ``False``, ``scalars().all()`` returns
                each row's first element.
        """
        self._rows = rows
        self._scalar_mode = scalar_mode

    def scalar_one_or_none(self) -> Any:
        """Return the single row (or ``None``) when exactly one result is expected."""
        if not self._rows:
            return None
        return self._rows[0]

    def scalars(self) -> _FakeResult:
        """Return ``self`` — ``.all()`` downstream returns unwrapped rows."""
        return _FakeResult(rows=list(self._rows), scalar_mode=True)

    def all(self) -> list[Any]:
        """Return rows as a list."""
        return list(self._rows)


class FakeSession:
    """In-memory async session double used by the service unit tests.

    The store is a pair of lists — one for :class:`AccountCode` rows and
    one for :class:`ActualExpense` rows. :meth:`execute` routes by
    inspecting the compiled SQL; any unexpected shape raises
    :class:`AssertionError` so the test surface stays tight.
    """

    def __init__(self) -> None:
        """Initialize empty stores + counters."""
        self.account_codes: list[AccountCode] = []
        self.actual_expenses: list[ActualExpense] = []
        self._pending: list[Any] = []
        self.commits: int = 0
        self.rollbacks: int = 0
        self.deleted_actual_cycle_ids: list[UUID] = []

    # ------------------------------------------------------------ ORM
    def add(self, obj: Any) -> None:
        """Queue an ORM instance for the next :meth:`commit`."""
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        self._pending.append(obj)

    async def commit(self) -> None:
        """Flush pending adds into the appropriate store list."""
        for obj in self._pending:
            if isinstance(obj, AccountCode):
                # Replace existing row with same code when present.
                existing_idx = next(
                    (i for i, row in enumerate(self.account_codes) if row.code == obj.code),
                    None,
                )
                if existing_idx is None:
                    self.account_codes.append(obj)
                else:
                    self.account_codes[existing_idx] = obj
            elif isinstance(obj, ActualExpense):
                self.actual_expenses.append(obj)
            else:  # pragma: no cover — defensive
                raise AssertionError(f"Unexpected ORM type added: {type(obj).__name__}")
        self._pending.clear()
        self.commits += 1

    async def rollback(self) -> None:
        """Discard pending adds."""
        self._pending.clear()
        self.rollbacks += 1

    async def flush(self) -> None:
        """No-op flush — :meth:`commit` already materializes the store."""
        return None

    async def refresh(self, _obj: Any) -> None:
        """No-op refresh — our fakes already carry their server-side defaults."""
        return None

    async def close(self) -> None:
        """No-op close."""
        return None

    # --------------------------------------------------------- execute
    async def execute(self, stmt: Any) -> _FakeResult:
        """Route a compiled statement to the right in-memory lookup.

        Recognised shapes:

        * ``SELECT FROM account_codes WHERE code = :code`` — upsert.
        * ``SELECT FROM account_codes ORDER BY code`` — list, with
          optional ``WHERE category = :cat`` filter.
        * ``SELECT code FROM account_codes WHERE category = :cat`` —
          ``get_codes_by_category`` / ``get_operational_codes_set``.
        * ``SELECT code FROM account_codes`` (no where) — all codes.
        * ``SELECT code, id FROM account_codes WHERE code IN (...)`` —
          code→id map.
        * ``DELETE FROM actual_expenses WHERE cycle_id = :cid``.
        * ``SELECT code, id FROM org_units`` — handled via ``org_units``
          table (stored on the instance as ``org_units``).

        Args:
            stmt: Compiled SQLAlchemy statement.

        Returns:
            _FakeResult: In-memory result matching the service's access pattern.
        """
        compiled = str(stmt)
        params = _extract_params(stmt)

        if compiled.startswith("DELETE FROM actual_expenses"):
            target = params.get("cycle_id_1") or params.get("cycle_id")
            if target is None:
                raise AssertionError(f"Unexpected DELETE shape: {compiled}")
            if isinstance(target, str):
                target = UUID(target)
            self.deleted_actual_cycle_ids.append(target)
            self.actual_expenses = [r for r in self.actual_expenses if r.cycle_id != target]
            return _FakeResult(rows=[])

        if "FROM account_codes" in compiled:
            return self._query_account_codes(compiled, params)

        if "FROM org_units" in compiled:
            units = getattr(self, "org_units", [])
            return _FakeResult(rows=[(u.code, u.id) for u in units])

        raise AssertionError(f"Unhandled statement in FakeSession: {compiled}")

    # ------------------------------------------------------------- helpers
    def _query_account_codes(
        self,
        compiled: str,
        params: dict[str, Any],
    ) -> _FakeResult:
        """Run a SELECT against the in-memory ``account_codes`` store."""
        rows = list(self.account_codes)

        # Filter: WHERE code = :code_1
        code_filter = params.get("code_1")
        if code_filter is not None and "account_codes.code =" in compiled:
            rows = [r for r in rows if r.code == code_filter]

        # Filter: WHERE category = :category_1
        category_filter = params.get("category_1")
        if category_filter is not None and "account_codes.category =" in compiled:
            cat_val = (
                category_filter.value
                if isinstance(category_filter, AccountCategory)
                else category_filter
            )
            rows = [r for r in rows if r.category.value == cat_val]

        # Filter: WHERE code IN (...)
        if "account_codes.code IN" in compiled:
            in_values: set[Any] = set()
            for key, value in params.items():
                if not key.startswith("code_") or value is None:
                    continue
                if isinstance(value, (list, tuple, set, frozenset)):
                    in_values.update(value)
                else:
                    in_values.add(value)
            if in_values:
                rows = [r for r in rows if r.code in in_values]

        rows.sort(key=lambda r: r.code)

        # Projection: SELECT code (FROM account_codes)
        if "SELECT account_codes.code, account_codes.id" in compiled:
            return _FakeResult(rows=[(r.code, r.id) for r in rows])
        if "SELECT account_codes.code " in compiled or compiled.startswith(
            "SELECT account_codes.code\n"
        ):
            return _FakeResult(rows=[(r.code,) for r in rows])
        # Default: full row projection — return as scalar_one_or_none / scalars.
        return _FakeResult(rows=rows)


def _extract_params(stmt: Any) -> dict[str, Any]:
    """Pull bound-parameter values out of a compiled SQLAlchemy statement.

    Args:
        stmt: Statement whose bound params are of interest.

    Returns:
        dict[str, Any]: Parameter name → value map (best effort).
    """
    try:
        compiled = stmt.compile(compile_kwargs={"literal_binds": False})
        return dict(compiled.params)
    except Exception:  # pragma: no cover — defensive
        return {}


class _FakeOrgUnit:
    """Minimal org-unit stand-in for ``org_unit_code_to_id_map`` lookups."""

    def __init__(self, code: str) -> None:
        """Store the code + fresh UUID."""
        self.code = code
        self.id = uuid4()


# --------------------------------------------------------------------- fixtures
@pytest.fixture
def fake_session() -> FakeSession:
    """Return a fresh in-memory :class:`FakeSession`."""
    session = FakeSession()
    session.org_units = [  # type: ignore[attr-defined]
        _FakeOrgUnit("4000"),
        _FakeOrgUnit("4023"),
    ]
    return session


@pytest.fixture
def system_admin() -> User:
    """Return a detached :class:`User` with the SystemAdmin role."""
    user = User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=b"\x00" * 32,
        name="Test Admin",
        email_enc=b"",
        email_hash=b"\x00" * 32,
        roles=[Role.SystemAdmin.value],
        org_unit_id=None,
        is_active=True,
    )
    return user


class _FakeAudit:
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
        """Record a call without touching any DB."""
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
async def account_service(
    fake_session: FakeSession,
) -> AsyncIterator[Any]:
    """Yield an :class:`AccountService` wired to the fake session + fake audit."""
    from app.domain.accounts.service import AccountService

    service = AccountService(fake_session)  # type: ignore[arg-type]
    service._audit = _FakeAudit()  # type: ignore[assignment]
    yield service


def make_account_code(
    *,
    code: str,
    name: str = "Test",
    category: AccountCategory = AccountCategory.operational,
    level: int = 1,
) -> AccountCode:
    """Return a detached :class:`AccountCode` ready for ``FakeSession`` seeding."""
    row = AccountCode(
        code=code,
        name=name,
        category=category,
        level=level,
        is_active=True,
    )
    row.id = uuid4()
    return row
