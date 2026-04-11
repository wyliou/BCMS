"""Unit tests for :mod:`app.domain._shared.queries` (§5.4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from app.domain._shared.queries import org_unit_code_to_id_map


@dataclass
class _FakeOrgUnit:
    """Minimal stand-in with just the columns used by the query."""

    id: UUID
    code: str


class _FakeResult:
    """Fake SQLAlchemy ``Result`` returning pre-seeded rows."""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        """Store the seeded rows."""
        self._rows = rows

    def all(self) -> list[tuple[Any, ...]]:
        """Return seeded rows."""
        return list(self._rows)


class _FakeSession:
    """In-memory async session double for :func:`org_unit_code_to_id_map`.

    The helper issues a single ``select(OrgUnit.code, OrgUnit.id)`` call
    — the fake returns the seeded rows verbatim regardless of the
    statement.
    """

    def __init__(self, units: list[_FakeOrgUnit]) -> None:
        """Seed the fake with pre-made :class:`_FakeOrgUnit` rows."""
        self._units = units
        self.execute_calls: int = 0

    async def execute(self, _stmt: Any) -> _FakeResult:
        """Return a fake result mirroring ``select(code, id)``."""
        self.execute_calls += 1
        return _FakeResult(rows=[(u.code, u.id) for u in self._units])


async def test_org_unit_code_to_id_map_happy_path() -> None:
    """Seed 3 units; the returned dict has 3 entries mapping code → UUID."""
    ids = [uuid4(), uuid4(), uuid4()]
    session = _FakeSession(
        [
            _FakeOrgUnit(id=ids[0], code="1000"),
            _FakeOrgUnit(id=ids[1], code="4000"),
            _FakeOrgUnit(id=ids[2], code="4023"),
        ]
    )
    result = await org_unit_code_to_id_map(session)  # type: ignore[arg-type]
    assert result == {"1000": ids[0], "4000": ids[1], "4023": ids[2]}


async def test_org_unit_code_to_id_map_empty_table() -> None:
    """An empty table returns an empty dict (not an error)."""
    session = _FakeSession([])
    result = await org_unit_code_to_id_map(session)  # type: ignore[arg-type]
    assert result == {}


async def test_org_unit_code_to_id_map_unknown_code_absent() -> None:
    """Codes not in the seed are absent from the returned dict."""
    unit_id = uuid4()
    session = _FakeSession([_FakeOrgUnit(id=unit_id, code="1000")])
    result = await org_unit_code_to_id_map(session)  # type: ignore[arg-type]
    assert "9999" not in result
    assert result["1000"] == unit_id


async def test_org_unit_code_to_id_map_single_query() -> None:
    """Two consecutive calls each emit exactly one execute (no caching)."""
    session = _FakeSession([_FakeOrgUnit(id=uuid4(), code="1000")])
    await org_unit_code_to_id_map(session)  # type: ignore[arg-type]
    await org_unit_code_to_id_map(session)  # type: ignore[arg-type]
    assert session.execute_calls == 2
