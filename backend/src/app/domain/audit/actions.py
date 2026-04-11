"""Single-source-of-truth :class:`AuditAction` enum (CR-002 owner).

This module owns **CR-002**: every ``audit.record(...)`` call across the
backend must pass a member of :class:`AuditAction` — no bare string literals.
New action verbs are added here and nowhere else. Downstream services import
:class:`AuditAction` from this module; the spec (``specs/domain_audit.md``)
is the canonical seed list for the enum members.

The enum intentionally subclasses :class:`str` (via :class:`~enum.StrEnum`)
so that each member is interchangeable with its ``str`` value — the value is
what actually gets written to ``audit_logs.action`` and fed into the hash
chain payload.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["AuditAction"]


class AuditAction(StrEnum):
    """Canonical enum of every recordable audit event in BCMS.

    Values are UPPER_SNAKE strings. This enum is the ONLY place where audit
    action strings may be defined — downstream services must never pass raw
    strings to :meth:`AuditService.record`.

    Members are seeded from ``specs/domain_audit.md`` (Batch 1 export table)
    and ``docs/architecture.md §8``. New verbs introduced by later batches
    are appended here; the enum is closed (no dynamic members).
    """

    # --- authentication / session -----------------------------------------
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_AUTHORIZE_FAILED = "LOGIN_AUTHORIZE_FAILED"
    LOGOUT = "LOGOUT"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    RBAC_DENIED = "RBAC_DENIED"
    AUTH_FAILED = "AUTH_FAILED"

    # --- cycles ------------------------------------------------------------
    CYCLE_OPEN = "CYCLE_OPEN"
    CYCLE_CLOSE = "CYCLE_CLOSE"
    CYCLE_REOPEN = "CYCLE_REOPEN"
    CYCLE_CREATE = "CYCLE_CREATE"

    # --- templates ---------------------------------------------------------
    TEMPLATE_DOWNLOAD = "TEMPLATE_DOWNLOAD"
    TEMPLATE_REGENERATE = "TEMPLATE_REGENERATE"

    # --- budget uploads ----------------------------------------------------
    BUDGET_UPLOAD = "BUDGET_UPLOAD"
    BUDGET_UPLOAD_FAILED = "BUDGET_UPLOAD_FAILED"

    # --- personnel ---------------------------------------------------------
    PERSONNEL_IMPORT = "PERSONNEL_IMPORT"
    PERSONNEL_IMPORT_FAILED = "PERSONNEL_IMPORT_FAILED"

    # --- shared cost -------------------------------------------------------
    SHARED_COST_IMPORT = "SHARED_COST_IMPORT"
    SHARED_COST_IMPORT_FAILED = "SHARED_COST_IMPORT_FAILED"

    # --- actuals -----------------------------------------------------------
    ACTUALS_IMPORT = "ACTUALS_IMPORT"

    # --- notifications -----------------------------------------------------
    NOTIFY_SENT = "NOTIFY_SENT"
    NOTIFY_FAILED = "NOTIFY_FAILED"
    NOTIFY_RESENT = "NOTIFY_RESENT"
    RESUBMIT_REQUEST = "RESUBMIT_REQUEST"

    # --- reports / exports ------------------------------------------------
    REPORT_EXPORT_QUEUED = "REPORT_EXPORT_QUEUED"
    REPORT_EXPORT_COMPLETE = "REPORT_EXPORT_COMPLETE"
    REPORT_EXPORT_FAILED = "REPORT_EXPORT_FAILED"

    # --- audit self-events -------------------------------------------------
    CHAIN_VERIFIED = "CHAIN_VERIFIED"
    AUDIT_EXPORT = "AUDIT_EXPORT"

    # --- administration ----------------------------------------------------
    USER_ROLE_UPDATED = "USER_ROLE_UPDATED"
    ORG_UNIT_CREATED = "ORG_UNIT_CREATED"
    ORG_UNIT_UPDATED = "ORG_UNIT_UPDATED"
