"""Unit tests for :mod:`app.core.security.roles`."""

from __future__ import annotations

from app.core.security.roles import ResourceType, Role


def test_role_enum_has_expected_members() -> None:
    """All seven PRD §5 roles are defined and stringify to their names."""
    expected = {
        "SystemAdmin",
        "FinanceAdmin",
        "HRAdmin",
        "FilingUnitManager",
        "UplineReviewer",
        "CompanyReviewer",
        "ITSecurityAuditor",
    }
    assert {r.value for r in Role} == expected
    for name in expected:
        assert Role(name).value == name


def test_role_is_str_enum() -> None:
    """Role members are interchangeable with their string values."""
    assert Role.FinanceAdmin == "FinanceAdmin"
    assert str(Role.FinanceAdmin) == "FinanceAdmin"


def test_resource_type_enum_is_closed() -> None:
    """ResourceType enum contains exactly the eight documented keys."""
    expected = {
        "cycle",
        "org_unit",
        "budget_upload",
        "personnel_upload",
        "shared_cost_upload",
        "report",
        "audit_log",
        "user",
    }
    assert {r.value for r in ResourceType} == expected
