"""Shared fixtures for :mod:`app.domain.budget_uploads` unit tests.

Ships a small in-memory :class:`FakeSession` that matches the SQL
shapes emitted by :mod:`app.domain.budget_uploads.repo` and
:mod:`app.domain.budget_uploads.service`, plus workbook builders and
service stubs shared by the validator / service / api test modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.security.models import OrgUnit, User
from app.core.security.roles import Role
from app.domain.accounts.models import AccountCategory, AccountCode
from app.domain.audit.actions import AuditAction
from app.domain.budget_uploads.models import BudgetLine, BudgetUpload, UploadStatus
from app.domain.cycles.models import BudgetCycle, CycleState
from app.infra.excel import workbook_to_bytes, write_workbook


def _now() -> datetime:
    """Return a deterministic aware UTC timestamp."""
    return datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc)


@dataclass
class _FakeResult:
    """Minimal :class:`sqlalchemy.Result` stand-in.

    Attributes:
        rows: Underlying row list.
    """

    rows: list[Any] = field(default_factory=list)

    def scalar_one(self) -> Any:
        """Return the first scalar row (used by ``coalesce(max(...))``)."""
        return self.rows[0] if self.rows else 0

    def scalar_one_or_none(self) -> Any:
        """Return the first row (or ``None``) for singleton queries."""
        return self.rows[0] if self.rows else None

    def scalars(self) -> _FakeResult:
        """Return ``self`` — ``.all()`` yields scalar rows."""
        return _FakeResult(rows=list(self.rows))

    def first(self) -> Any:
        """Return the first row or ``None``."""
        return self.rows[0] if self.rows else None

    def all(self) -> list[Any]:
        """Return every row as a list."""
        return list(self.rows)


class FakeSession:
    """Async-session double for the budget uploads tier.

    Stores the five row types touched by the service / repo / validator
    in plain Python lists. SQL dispatch uses substring matching on the
    compiled statement text — unexpected shapes raise :class:`AssertionError`.
    """

    def __init__(self) -> None:
        """Initialize empty stores + commit counters."""
        self.account_codes: list[AccountCode] = []
        self.org_units: list[OrgUnit] = []
        self.cycles: dict[UUID, BudgetCycle] = {}
        self.budget_uploads: list[BudgetUpload] = []
        self.budget_lines: list[BudgetLine] = []
        self._pending: list[Any] = []
        self.commits: int = 0
        self.rollbacks: int = 0

    # ------------------------------------------------------------ add/commit
    def add(self, obj: Any) -> None:
        """Queue a row for :meth:`commit` / :meth:`flush`."""
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        self._pending.append(obj)

    async def commit(self) -> None:
        """Materialize pending adds into the matching store list."""
        self._flush_pending()
        self.commits += 1

    async def rollback(self) -> None:
        """Discard pending adds."""
        self._pending.clear()
        self.rollbacks += 1

    async def flush(self) -> None:
        """Materialize pending adds without bumping the commit counter."""
        self._flush_pending()

    async def refresh(self, _obj: Any) -> None:
        """No-op refresh."""
        return None

    async def close(self) -> None:
        """No-op close."""
        return None

    def _flush_pending(self) -> None:
        """Drop pending objects into the matching store list."""
        for obj in self._pending:
            if isinstance(obj, BudgetUpload):
                self.budget_uploads.append(obj)
            elif isinstance(obj, BudgetLine):
                self.budget_lines.append(obj)
            elif isinstance(obj, AccountCode):
                self.account_codes.append(obj)
            else:  # pragma: no cover — defensive
                raise AssertionError(f"Unexpected add: {type(obj).__name__}")
        self._pending.clear()

    async def get(self, model: Any, pk: Any) -> Any:
        """Route to the in-memory store for ``BudgetCycle`` / ``OrgUnit`` / ``BudgetUpload``."""
        if model is BudgetCycle:
            return self.cycles.get(pk)
        if model is OrgUnit:
            for unit in self.org_units:
                if unit.id == pk:
                    return unit
            return None
        if model is BudgetUpload:
            for upload in self.budget_uploads:
                if upload.id == pk:
                    return upload
            return None
        return None

    # ----------------------------------------------------------------- execute
    async def execute(self, stmt: Any) -> _FakeResult:
        """Dispatch on the compiled statement text."""
        compiled = str(stmt)
        params = _extract_params(stmt)

        # next_version: SELECT coalesce(max(version),0) FROM budget_uploads
        if "max(budget_uploads.version)" in compiled or "coalesce(max" in compiled.lower():
            cycle_id = params.get("cycle_id_1")
            org_unit_id = params.get("org_unit_id_1")
            matching = [
                row
                for row in self.budget_uploads
                if _coerce_uuid(row.cycle_id) == _coerce_uuid(cycle_id)
                and _coerce_uuid(row.org_unit_id) == _coerce_uuid(org_unit_id)
            ]
            current_max = max((row.version for row in matching), default=0)
            return _FakeResult(rows=[current_max])

        if "FROM org_units" in compiled:
            return _FakeResult(rows=[(u.code, u.id) for u in self.org_units])

        if "FROM account_codes" in compiled:
            rows = list(self.account_codes)
            # Category filter
            category_filter = params.get("category_1")
            if category_filter is not None and "account_codes.category" in compiled:
                cat_val = _enum_value(category_filter)
                rows = [r for r in rows if r.category.value == cat_val]
            # IN (...) filter on code
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
            # Projection SELECT code, id
            if "SELECT account_codes.code, account_codes.id" in compiled:
                return _FakeResult(rows=[(r.code, r.id) for r in rows])
            if "SELECT account_codes.code" in compiled:
                return _FakeResult(rows=[(r.code,) for r in rows])
            return _FakeResult(rows=rows)

        if "FROM budget_uploads" in compiled:
            cycle_id = params.get("cycle_id_1")
            org_unit_id = params.get("org_unit_id_1")
            rows = list(self.budget_uploads)
            if cycle_id is not None:
                rows = [r for r in rows if _coerce_uuid(r.cycle_id) == _coerce_uuid(cycle_id)]
            if org_unit_id is not None and "org_unit_id =" in compiled:
                rows = [r for r in rows if _coerce_uuid(r.org_unit_id) == _coerce_uuid(org_unit_id)]
            rows.sort(key=lambda r: r.version, reverse=True)
            return _FakeResult(rows=rows)

        if "FROM budget_lines" in compiled:
            in_values: set[Any] = set()
            for key, value in params.items():
                if not key.startswith("upload_id_") or value is None:
                    continue
                if isinstance(value, (list, tuple, set, frozenset)):
                    in_values.update(value)
                else:
                    in_values.add(value)
            if in_values:
                rows = [
                    line
                    for line in self.budget_lines
                    if _coerce_uuid(line.upload_id) in {_coerce_uuid(v) for v in in_values}
                ]
            else:
                rows = list(self.budget_lines)
            return _FakeResult(rows=rows)

        if "FROM budget_cycles" in compiled:
            target = params.get("pk_1") or params.get("id_1")
            row = self.cycles.get(_coerce_uuid(target))
            return _FakeResult(rows=[row] if row is not None else [])

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
    except (ValueError, TypeError):
        return value


def _enum_value(value: Any) -> str:
    """Return the raw string for an enum or a plain string."""
    return getattr(value, "value", value)


# ----------------------------------------------------------------- factories
def make_account(
    *,
    code: str,
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


def make_org_unit(*, code: str = "4023", name: str = "業務部") -> OrgUnit:
    """Return a detached filing :class:`OrgUnit`."""
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


def make_cycle(*, fiscal_year: int = 2026, state: CycleState = CycleState.open) -> BudgetCycle:
    """Return a detached :class:`BudgetCycle` in ``state``."""
    cycle = BudgetCycle(
        fiscal_year=fiscal_year,
        deadline=date(fiscal_year, 12, 31),
        reporting_currency="TWD",
        status=state.value,
        created_by=uuid4(),
        created_at=_now(),
        updated_at=_now(),
    )
    cycle.id = uuid4()
    cycle.opened_at = _now() if state == CycleState.open else None
    return cycle


def make_user(
    *,
    role: Role = Role.FilingUnitManager,
    org_unit_id: UUID | None = None,
    email: str = "tester@example.com",
) -> User:
    """Return a detached :class:`User`. ``email`` stored as UTF-8 bytes."""
    user = User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=b"\x00" * 32,
        name="Test",
        email_enc=email.encode("utf-8"),
        email_hash=b"\x00" * 32,
        roles=[role.value],
        org_unit_id=org_unit_id,
        is_active=True,
    )
    return user


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


class FakeCycleService:
    """Stub :class:`CycleService` that only honours ``assert_open``."""

    def __init__(self, *, open_cycles: set[UUID] | None = None) -> None:
        """Initialize with the set of cycle ids considered Open."""
        self.open_cycles = open_cycles or set()
        self.assert_calls: list[UUID] = []

    async def assert_open(self, cycle_id: UUID) -> None:
        """Raise :class:`AppError` ``CYCLE_004`` when the id is not Open."""
        self.assert_calls.append(cycle_id)
        if cycle_id not in self.open_cycles:
            from app.core.errors import AppError

            raise AppError("CYCLE_004", f"cycle {cycle_id} not open")


class FakeAccountService:
    """Stub :class:`AccountService` returning a fixed operational set."""

    def __init__(self, codes: set[str]) -> None:
        """Initialize with the fixed code set."""
        self.codes = set(codes)

    async def get_operational_codes_set(self) -> set[str]:
        """Return the fixed operational code set."""
        return set(self.codes)


class FakeNotificationService:
    """In-memory stand-in for :class:`NotificationService`.

    Records every :meth:`send` call. When :attr:`fail` is set, raises
    :class:`InfraError` so the service exercises the CR-029 path.
    """

    def __init__(self) -> None:
        """Initialize empty call log."""
        self.calls: list[dict[str, Any]] = []
        self.fail: bool = False

    async def send(
        self,
        *,
        template: Any,
        recipient_user_id: UUID,
        recipient_email: str,
        context: dict[str, Any],
        related: tuple[str, UUID] | None = None,
    ) -> Any:
        """Capture the call or raise per :attr:`fail`."""
        self.calls.append(
            {
                "template": template,
                "recipient_user_id": recipient_user_id,
                "recipient_email": recipient_email,
                "context": dict(context),
                "related": related,
            }
        )
        if self.fail:
            from app.core.errors import InfraError

            raise InfraError("NOTIFY_001", "smtp boom")
        return object()


class FakeStorage:
    """Capture-and-replay storage stand-in for the service test tier."""

    def __init__(self) -> None:
        """Initialize empty stores."""
        self.files: dict[str, bytes] = {}
        self.save_calls: list[tuple[str, str, int]] = []
        self._counter = 0

    async def save(self, category: str, filename: str, content: bytes) -> str:
        """Fake :func:`app.infra.storage.save`."""
        self.save_calls.append((category, filename, len(content)))
        self._counter += 1
        key = f"{category}/test/{self._counter:04d}_{filename}"
        self.files[key] = bytes(content)
        return key


# ---------------------------------------------------- workbook fixtures
def build_valid_workbook(
    *,
    dept_code: str,
    rows: list[tuple[str, str, str, object]],
) -> bytes:
    """Build a minimal valid budget upload workbook in-memory.

    Layout mirrors :func:`app.domain.templates.builder.build_template_workbook`
    — header sheet with ``dept_code`` in ``B2`` plus an accounts sheet
    with the four-column header.

    Args:
        dept_code: Org unit code to write into cell ``B2``.
        rows: ``(account_code, account_name, prior_actual, budget_amount)``
            tuples. ``budget_amount`` may be any type openpyxl accepts.

    Returns:
        bytes: Raw ``.xlsx`` content.
    """
    workbook = write_workbook()
    header = workbook.active
    assert header is not None
    header.title = "header"
    header["A2"] = "dept_code"
    header["B2"] = dept_code
    accounts = workbook.create_sheet("accounts")
    accounts.cell(row=1, column=1, value="account_code")
    accounts.cell(row=1, column=2, value="account_name")
    accounts.cell(row=1, column=3, value="prior_actual")
    accounts.cell(row=1, column=4, value="budget_amount")
    for index, (code, name, prior, amount) in enumerate(rows, start=2):
        accounts.cell(row=index, column=1, value=code)
        accounts.cell(row=index, column=2, value=name)
        accounts.cell(row=index, column=3, value=prior)
        accounts.cell(row=index, column=4, value=amount)
    return workbook_to_bytes(workbook)


@pytest.fixture
def fake_session() -> FakeSession:
    """Return a fresh in-memory :class:`FakeSession`."""
    return FakeSession()


# Re-exports used by api test module
__all__ = [
    "FakeAccountService",
    "FakeAudit",
    "FakeCycleService",
    "FakeNotificationService",
    "FakeSession",
    "FakeStorage",
    "UploadStatus",
    "build_valid_workbook",
    "make_account",
    "make_cycle",
    "make_org_unit",
    "make_user",
]
