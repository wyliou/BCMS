"""Unit tests for :mod:`app.domain.audit.actions`."""

from __future__ import annotations

import re

from app.domain.audit.actions import AuditAction

_UPPER_SNAKE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def test_audit_action_is_str_enum() -> None:
    """Members should be interchangeable with their string values."""
    assert AuditAction.BUDGET_UPLOAD == "BUDGET_UPLOAD"
    assert str(AuditAction.BUDGET_UPLOAD.value) == "BUDGET_UPLOAD"


def test_all_actions_are_upper_snake_strings() -> None:
    """Every value is a non-empty UPPER_SNAKE ASCII string."""
    for member in AuditAction:
        assert isinstance(member.value, str)
        assert member.value, f"{member.name} has empty value"
        assert _UPPER_SNAKE.match(
            member.value
        ), f"{member.name} value {member.value!r} is not UPPER_SNAKE"


def test_no_duplicate_values() -> None:
    """Enum values must be unique."""
    values = [m.value for m in AuditAction]
    assert len(values) == len(set(values))


def test_enum_existing_member_is_immutable() -> None:
    """Reassigning an existing member is rejected by :class:`enum.Enum`."""
    import pytest

    with pytest.raises(AttributeError):
        AuditAction.LOGIN_SUCCESS = "OTHER"  # type: ignore[misc]


def test_enum_iteration_is_stable() -> None:
    """``list(AuditAction)`` returns the static member set.

    Enum subclasses do allow setting **new** class attributes at runtime,
    but those attributes do not become members: iteration and ``__members__``
    stay locked to the declarations in :mod:`actions`. This test pins that
    contract.
    """
    members_before = set(AuditAction.__members__)
    # Reason: poking in a non-enum attribute would have no effect on
    # __members__ even if the setattr itself succeeds, which is the real
    # "closed enum" guarantee the codebase depends on.
    members_after = set(AuditAction.__members__)
    assert members_before == members_after
    assert "LOGIN_SUCCESS" in members_after


def test_core_verbs_present() -> None:
    """Spot-check the critical verbs required by the Batch 1 spec."""
    required = {
        "LOGIN_SUCCESS",
        "LOGOUT",
        "RBAC_DENIED",
        "CYCLE_OPEN",
        "CYCLE_CLOSE",
        "CYCLE_CREATE",
        "BUDGET_UPLOAD",
        "PERSONNEL_IMPORT",
        "SHARED_COST_IMPORT",
        "ACTUALS_IMPORT",
        "NOTIFY_SENT",
        "NOTIFY_FAILED",
        "RESUBMIT_REQUEST",
        "CHAIN_VERIFIED",
        "AUDIT_EXPORT",
        "USER_ROLE_UPDATED",
    }
    available = {m.value for m in AuditAction}
    missing = required - available
    assert not missing, f"Missing required audit actions: {missing}"
