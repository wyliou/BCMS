"""Unit tests for :mod:`app.core.security.rbac` (CR-011, CR-032, CR-033)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.security.rbac import ALL_SCOPES, scoped_org_units
from app.core.security.roles import Role

from .conftest import FakeDB, FakeOrgUnit, make_user


async def test_scoped_org_units_system_admin_returns_all_scopes() -> None:
    """SystemAdmin bypasses the scope filter entirely."""
    user = make_user(Role.SystemAdmin)
    result = await scoped_org_units(user, FakeDB())  # type: ignore[arg-type]
    assert result is ALL_SCOPES


async def test_scoped_org_units_finance_admin_returns_all_scopes() -> None:
    """FinanceAdmin bypasses the scope filter entirely."""
    user = make_user(Role.FinanceAdmin)
    result = await scoped_org_units(user, FakeDB())  # type: ignore[arg-type]
    assert result is ALL_SCOPES


async def test_scoped_org_units_hr_admin_returns_all_scopes() -> None:
    """HRAdmin is global per architecture §5 (personnel import)."""
    user = make_user(Role.HRAdmin)
    result = await scoped_org_units(user, FakeDB())  # type: ignore[arg-type]
    assert result is ALL_SCOPES


async def test_scoped_org_units_it_security_auditor_returns_all_scopes() -> None:
    """ITSecurityAuditor is global (audit log read)."""
    user = make_user(Role.ITSecurityAuditor)
    result = await scoped_org_units(user, FakeDB())  # type: ignore[arg-type]
    assert result is ALL_SCOPES


async def test_scoped_org_units_filing_unit_manager_is_single_unit() -> None:
    """FilingUnitManager sees only its own org unit."""
    org_id = uuid4()
    user = make_user(Role.FilingUnitManager, org_unit_id=org_id)
    result = await scoped_org_units(user, FakeDB())  # type: ignore[arg-type]
    assert result == {org_id}


async def test_scoped_org_units_filing_unit_manager_no_org_is_empty() -> None:
    """A FilingUnitManager without an org unit sees nothing."""
    user = make_user(Role.FilingUnitManager, org_unit_id=None)
    result = await scoped_org_units(user, FakeDB())  # type: ignore[arg-type]
    assert result == set()


async def test_scoped_org_units_company_reviewer_returns_root() -> None:
    """CompanyReviewer sees the 0000公司 root org unit."""
    root = FakeOrgUnit(id=uuid4(), code="0000", level_code="0000", parent_id=None)
    other = FakeOrgUnit(id=uuid4(), code="1000", level_code="1000", parent_id=root.id)
    db = FakeDB(org_units=[root, other])
    user = make_user(Role.CompanyReviewer)
    result = await scoped_org_units(user, db)  # type: ignore[arg-type]
    assert result == {root.id}


async def test_scoped_org_units_upline_reviewer_walks_descendants() -> None:
    """UplineReviewer returns its own unit plus every descendant."""
    root = FakeOrgUnit(id=uuid4(), code="0000", level_code="0000", parent_id=None)
    upline = FakeOrgUnit(id=uuid4(), code="1000", level_code="1000", parent_id=root.id)
    child_a = FakeOrgUnit(id=uuid4(), code="2000", level_code="2000", parent_id=upline.id)
    child_b = FakeOrgUnit(id=uuid4(), code="4000", level_code="4000", parent_id=child_a.id)
    unrelated = FakeOrgUnit(id=uuid4(), code="5000", level_code="5000", parent_id=root.id)
    db = FakeDB(org_units=[root, upline, child_a, child_b, unrelated])
    user = make_user(Role.UplineReviewer, org_unit_id=upline.id)
    result = await scoped_org_units(user, db)  # type: ignore[arg-type]
    assert result == {upline.id, child_a.id, child_b.id}


async def test_scoped_org_units_upline_reviewer_no_org_is_empty() -> None:
    """UplineReviewer without an org unit yields an empty set."""
    user = make_user(Role.UplineReviewer, org_unit_id=None)
    result = await scoped_org_units(user, FakeDB())  # type: ignore[arg-type]
    assert result == set()


def test_role_parsing_from_roles_jsonb_fallback() -> None:
    """Users.role returns None when the JSONB array is empty."""
    user = make_user(Role.FilingUnitManager)
    user.roles = []
    assert user.role is None
    assert user.role_set() == set()


def test_role_property_returns_first_enum_member() -> None:
    """Users.role returns the first parseable Role from the JSONB array."""
    user = make_user(Role.FilingUnitManager)
    user.roles = ["NotARole", "FinanceAdmin", "SystemAdmin"]
    assert user.role == Role.FinanceAdmin
    assert user.role_set() == {Role.FinanceAdmin, Role.SystemAdmin}


@pytest.mark.parametrize("role", list(Role))
async def test_every_role_has_a_defined_scope(role: Role) -> None:
    """Every role in the enum resolves to either ALL_SCOPES or a concrete set."""
    user = make_user(role, org_unit_id=uuid4())
    root = FakeOrgUnit(id=uuid4(), code="0000", level_code="0000", parent_id=None)
    db = FakeDB(org_units=[root])
    result = await scoped_org_units(user, db)  # type: ignore[arg-type]
    assert result is ALL_SCOPES or isinstance(result, set)
