"""Unit tests for :mod:`app.domain.cycles.filing_units`."""

from __future__ import annotations

from uuid import uuid4

from app.core.security.roles import Role
from app.domain.cycles.filing_units import list_filing_units
from tests.unit.cycles.conftest import FakeSession, make_org_unit, make_user


async def test_list_filing_units_includes_no_manager_rows(fake_session: FakeSession) -> None:
    """Filing units without a manager are returned with ``has_manager=False``."""
    cycle_id = uuid4()
    managed = make_org_unit(code="4000")
    unmanaged = make_org_unit(code="4010")
    fake_session.org_units = [managed, unmanaged]
    fake_session.users = [
        make_user(roles=[Role.FilingUnitManager], org_unit_id=managed.id),
    ]

    result = await list_filing_units(fake_session, cycle_id)  # type: ignore[arg-type]

    codes = [info.code for info in result]
    assert codes == ["4000", "4010"]  # sorted by code
    by_code = {info.code: info for info in result}
    assert by_code["4000"].has_manager is True
    assert by_code["4010"].has_manager is False
    assert by_code["4010"].warnings == ["missing-manager"]


async def test_list_filing_units_excludes_non_filing_units(fake_session: FakeSession) -> None:
    """Rows with ``is_filing_unit=False`` or ``level_code='0000'`` are filtered."""
    cycle_id = uuid4()
    fake_session.org_units = [
        make_org_unit(code="4000", level_code="4000", is_filing_unit=True),
        make_org_unit(code="0000", level_code="0000", is_filing_unit=True),  # root: filtered
        make_org_unit(code="5000", level_code="5000", is_filing_unit=False),
    ]
    fake_session.users = []
    result = await list_filing_units(fake_session, cycle_id)  # type: ignore[arg-type]
    assert [info.code for info in result] == ["4000"]


async def test_list_filing_units_honours_excluded_for_cycle(
    fake_session: FakeSession,
) -> None:
    """Units listing the cycle id in ``excluded_for_cycle_ids`` flag ``excluded=True``."""
    cycle_id = uuid4()
    excluded_unit = make_org_unit(code="4000", excluded_for_cycle_ids=[str(cycle_id)])
    normal_unit = make_org_unit(code="4010")
    fake_session.org_units = [excluded_unit, normal_unit]
    fake_session.users = [
        make_user(roles=[Role.FilingUnitManager], org_unit_id=normal_unit.id),
    ]

    result = await list_filing_units(fake_session, cycle_id)  # type: ignore[arg-type]
    by_code = {info.code: info for info in result}
    assert by_code["4000"].excluded is True
    assert by_code["4010"].excluded is False
    # CR-008: excluded rows without managers produce NO "missing-manager" warning.
    assert by_code["4000"].warnings == []
