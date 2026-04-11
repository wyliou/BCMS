"""Shared fixtures for :mod:`app.core.security` unit tests.

The security unit tier avoids Postgres/aiosqlite so these fixtures
expose minimal in-memory doubles for the handful of DB-facing calls
that :mod:`app.core.security.rbac` makes (``db.execute`` against
``select(OrgUnit.id)`` — nothing else). Real unit behavior is
exercised against the in-memory double; the integration tier uses
the real Postgres engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from app.core.security.models import User
from app.core.security.roles import Role


@dataclass
class FakeOrgUnit:
    """Minimal stand-in for :class:`app.core.security.models.OrgUnit`.

    Attributes:
        id (UUID): Primary key.
        code (str): Human-readable code.
        level_code (str): Level code ("0000", "1000", ...).
        parent_id (UUID | None): Parent org-unit id.
    """

    id: UUID
    code: str
    level_code: str
    parent_id: UUID | None


@dataclass
class FakeExecuteResult:
    """Container mimicking the subset of SQLAlchemy ``Result`` used by rbac."""

    rows: list[tuple[Any, ...]]

    def all(self) -> list[tuple[Any, ...]]:
        """Return every row."""
        return list(self.rows)


@dataclass
class FakeDB:
    """In-memory fake :class:`AsyncSession` used by RBAC unit tests.

    Attributes:
        org_units (list[FakeOrgUnit]): Seeded org units. ``execute``
            inspects the compiled SQL to decide which rows to return
            for the supported query shapes.
    """

    org_units: list[FakeOrgUnit] = field(default_factory=list)

    async def execute(self, stmt: Any) -> FakeExecuteResult:
        """Return org-unit ids matching the supported query shapes.

        The RBAC module issues two query shapes against ``org_units``:

        1. ``SELECT id FROM org_units WHERE level_code = '0000'`` — used
           by :class:`CompanyReviewer` scope.
        2. ``SELECT id FROM org_units WHERE parent_id IN (:ids)`` — used
           by :class:`UplineReviewer` descendant walk.

        Args:
            stmt (Any): Compiled SQLAlchemy statement.

        Returns:
            FakeExecuteResult: Matching ``(id,)`` rows.
        """
        compiled = str(stmt)
        if "level_code" in compiled:
            roots = [u.id for u in self.org_units if u.level_code == "0000"]
            return FakeExecuteResult(rows=[(rid,) for rid in roots])

        # Assume the descendant walk: pull parent ids from the bound
        # parameters by inspecting the compiled statement's .whereclause.
        params = _extract_parent_ids(stmt)
        matches = [u.id for u in self.org_units if u.parent_id in params]
        return FakeExecuteResult(rows=[(mid,) for mid in matches])


def _extract_parent_ids(stmt: Any) -> set[UUID]:
    """Best-effort extraction of the ``parent_id IN (...)`` param values.

    SQLAlchemy 2.x exposes the bound parameters via
    ``stmt.compile().params`` — for ``IN`` clauses the binds are named
    ``parent_id_1_1``, ``parent_id_1_2``, etc. We grab every UUID-valued
    param and return it as a set.

    Args:
        stmt (Any): Compiled statement.

    Returns:
        set[UUID]: Values found in the bound parameters.
    """
    result: set[UUID] = set()

    def _absorb(value: Any) -> None:
        if isinstance(value, UUID):
            result.add(value)
        elif isinstance(value, str):
            try:
                result.add(UUID(value))
            except ValueError:
                return
        elif isinstance(value, (list, tuple, set, frozenset)):
            for sub in value:
                _absorb(sub)

    try:
        compiled = stmt.compile(compile_kwargs={"literal_binds": False})
        for value in compiled.params.values():
            _absorb(value)
    except Exception:  # noqa: S110  # pragma: no cover — best-effort fallback
        pass

    # Reason: SQLAlchemy uses expanding binds for ``IN`` clauses that are
    # not surfaced in compiled.params for postcompile use. Fall back to
    # walking ``stmt.whereclause`` for any ``BindParameter`` value.
    try:
        where = getattr(stmt, "whereclause", None)
        if where is not None:
            from sqlalchemy.sql.elements import BindParameter  # local import

            for elem in where.get_children():
                if isinstance(elem, BindParameter):
                    _absorb(elem.value)
            if isinstance(where, BindParameter):
                _absorb(where.value)
    except Exception:  # noqa: S110  # pragma: no cover — best-effort fallback
        pass
    return result


def make_user(role: Role, org_unit_id: UUID | None = None) -> User:
    """Return an in-memory :class:`User` wired with a single role.

    Args:
        role (Role): Role to assign.
        org_unit_id (UUID | None): Optional scoped org unit id.

    Returns:
        User: Detached SQLAlchemy instance (never flushed).
    """
    user = User(
        id=uuid4(),
        sso_id_enc=b"",
        sso_id_hash=b"\x00" * 32,
        name="Test User",
        email_enc=b"",
        email_hash=b"\x00" * 32,
        roles=[role.value],
        org_unit_id=org_unit_id,
        is_active=True,
    )
    return user
