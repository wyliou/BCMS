"""Single-source-of-truth :class:`Role` and :class:`ResourceType` enums (M10).

This module owns the canonical role list and the canonical resource-type
keys used by :mod:`app.core.security.rbac`. Both enums subclass
:class:`str` (via :class:`~enum.StrEnum`) so that each member is
interchangeable with its string value — the value is what gets serialized
into JWT claims, audit ``details`` dicts, and JSON API payloads.

The seven :class:`Role` members map 1:1 to PRD §5 / architecture §5. The
:class:`ResourceType` members enumerate the keys that ``require_scope``
accepts as its first argument; keeping them in an enum prevents string-
literal drift across route handlers.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["Role", "ResourceType"]


class Role(StrEnum):
    """Canonical system roles (FR-022, PRD §5, architecture §5).

    Every role below is enforced by :func:`app.core.security.rbac.require_role`
    and scoped by :func:`app.core.security.rbac.scoped_org_units`. The
    values are written into ``users.roles`` JSONB, JWT ``role`` claims,
    and audit-log ``details`` — always as their raw string values.
    """

    SystemAdmin = "SystemAdmin"
    FinanceAdmin = "FinanceAdmin"
    HRAdmin = "HRAdmin"
    FilingUnitManager = "FilingUnitManager"
    UplineReviewer = "UplineReviewer"
    CompanyReviewer = "CompanyReviewer"
    ITSecurityAuditor = "ITSecurityAuditor"


class ResourceType(StrEnum):
    """Canonical resource-type keys for :func:`rbac.require_scope` (CR-032).

    Each value corresponds to a resource-id path parameter that a route
    handler may declare. Keeping the enum closed ensures that ad-hoc
    string literals can't slip into route declarations.
    """

    cycle = "cycle"
    org_unit = "org_unit"
    budget_upload = "budget_upload"
    personnel_upload = "personnel_upload"
    shared_cost_upload = "shared_cost_upload"
    report = "report"
    audit_log = "audit_log"
    user = "user"
