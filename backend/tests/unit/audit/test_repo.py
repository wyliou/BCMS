"""Unit tests for :mod:`app.domain.audit.repo` — filter validation only.

The real repository's read/write paths require a live async SQL engine
and are exercised in ``tests/integration/audit/test_repo.py``. This unit
module pins down the behaviours that can be verified in pure Python:

* :meth:`AuditRepo._validate_filters` raises ``AUDIT_002`` on bad input.
* :meth:`AuditRepo._build_conditions` only emits predicates for fields
  that are actually set.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.domain.audit.repo import AuditFilters, AuditRepo


def test_validate_filters_accepts_defaults() -> None:
    """A default :class:`AuditFilters` passes validation."""
    AuditRepo._validate_filters(AuditFilters())


def test_validate_filters_rejects_bad_page() -> None:
    """``page < 1`` is an AUDIT_002."""
    with pytest.raises(AppError) as exc_info:
        AuditRepo._validate_filters(AuditFilters(page=0))
    assert exc_info.value.code == "AUDIT_002"


def test_validate_filters_rejects_bad_size() -> None:
    """Sizes outside [1, 200] raise AUDIT_002."""
    with pytest.raises(AppError):
        AuditRepo._validate_filters(AuditFilters(size=0))
    with pytest.raises(AppError):
        AuditRepo._validate_filters(AuditFilters(size=201))


def test_validate_filters_rejects_inverted_range() -> None:
    """``to_dt < from_dt`` raises AUDIT_002."""
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    end = datetime(2026, 5, 1, tzinfo=timezone.utc)
    with pytest.raises(AppError) as exc_info:
        AuditRepo._validate_filters(AuditFilters(from_dt=start, to_dt=end))
    assert exc_info.value.code == "AUDIT_002"


def test_build_conditions_empty_for_defaults() -> None:
    """Default filters should produce no predicates."""
    conditions = AuditRepo._build_conditions(AuditFilters())
    assert conditions == []


def test_build_conditions_all_filters_set() -> None:
    """Every non-None filter contributes exactly one predicate."""
    f = AuditFilters(
        user_id=uuid4(),
        action="LOGIN_SUCCESS",
        resource_type="session",
        resource_id=uuid4(),
        from_dt=datetime(2026, 1, 1, tzinfo=timezone.utc),
        to_dt=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )
    conditions = AuditRepo._build_conditions(f)
    assert len(conditions) == 6
