"""Unit tests for :class:`SharedCostImportValidator` (FR-027, CR-004)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.domain.shared_costs.validator import SharedCostImportValidator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ORG_CODES = {"4023": uuid4(), "4024": uuid4()}
_SHARED_CODES = {"SC001", "SC002", "SC003"}

_VALIDATOR = SharedCostImportValidator()


def _make_rows(
    dept_id: str = "4023",
    account_code: str = "SC001",
    amount: object = "1000",
) -> list[dict[str, object]]:
    """Build a single-row list with the given field values."""
    return [{"dept_id": dept_id, "account_code": account_code, "amount": amount}]


# ---------------------------------------------------------------------------
# SHARED_001 — unknown dept_id
# ---------------------------------------------------------------------------


def test_validate_shared_001_unknown_dept_id() -> None:
    """``dept_id`` not in org_unit_codes raises SHARED_001 at correct row."""
    rows = _make_rows(dept_id="9999")
    result = _VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_CODES,
        shared_cost_codes=_SHARED_CODES,
    )

    assert result.valid is False
    assert len(result.errors) == 1
    err = result.errors[0]
    assert err.code == "SHARED_001"
    assert err.column == "dept_id"
    assert err.row == 2
    assert "9999" in err.reason


def test_validate_shared_001_empty_dept_id() -> None:
    """Empty ``dept_id`` cell is also treated as unknown (SHARED_001)."""
    rows = _make_rows(dept_id="")
    result = _VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_CODES,
        shared_cost_codes=_SHARED_CODES,
    )
    assert result.valid is False
    assert result.errors[0].code == "SHARED_001"


# ---------------------------------------------------------------------------
# SHARED_002 — account_code not in shared_cost category
# ---------------------------------------------------------------------------


def test_validate_shared_002_wrong_account_category() -> None:
    """An operational code ``OP001`` not in shared_cost set → SHARED_002."""
    rows = _make_rows(account_code="OP001")
    result = _VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_CODES,
        shared_cost_codes=_SHARED_CODES,
    )

    assert result.valid is False
    assert len(result.errors) == 1
    err = result.errors[0]
    assert err.code == "SHARED_002"
    assert err.column == "account_code"
    assert err.row == 2
    assert "shared_cost" in err.reason


def test_validate_shared_002_empty_account_code() -> None:
    """Empty ``account_code`` also raises SHARED_002."""
    rows = _make_rows(account_code="")
    result = _VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_CODES,
        shared_cost_codes=_SHARED_CODES,
    )
    assert result.valid is False
    assert result.errors[0].code == "SHARED_002"


# ---------------------------------------------------------------------------
# SHARED_003 — amount invalid / zero / negative
# ---------------------------------------------------------------------------


def test_validate_shared_003_non_numeric_amount() -> None:
    """Non-numeric ``amount`` → SHARED_003 (CR-021)."""
    rows = _make_rows(amount="abc")
    result = _VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_CODES,
        shared_cost_codes=_SHARED_CODES,
    )

    assert result.valid is False
    assert len(result.errors) == 1
    err = result.errors[0]
    assert err.code == "SHARED_003"
    assert err.column == "amount"
    assert err.row == 2


def test_validate_shared_003_zero_amount_rejected() -> None:
    """Zero ``amount`` rejected with allow_zero=False (CR-012)."""
    rows = _make_rows(amount=0)
    result = _VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_CODES,
        shared_cost_codes=_SHARED_CODES,
    )

    assert result.valid is False
    err = result.errors[0]
    assert err.code == "SHARED_003"
    assert err.column == "amount"
    # Spec §7: reason must contain '> 0'
    assert "> 0" in err.reason


def test_validate_shared_003_negative_amount_rejected() -> None:
    """Negative ``amount`` is also rejected."""
    rows = _make_rows(amount="-500")
    result = _VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_CODES,
        shared_cost_codes=_SHARED_CODES,
    )

    assert result.valid is False
    assert result.errors[0].code == "SHARED_003"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_validate_all_valid_rows() -> None:
    """Three valid rows → ValidationResult.valid is True, rows non-empty."""
    rows = [
        {"dept_id": "4023", "account_code": "SC001", "amount": "1000"},
        {"dept_id": "4023", "account_code": "SC002", "amount": "2500.50"},
        {"dept_id": "4024", "account_code": "SC003", "amount": 300},
    ]
    result = _VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_CODES,
        shared_cost_codes=_SHARED_CODES,
    )

    assert result.valid is True
    assert len(result.errors) == 0
    assert len(result.rows) == 3

    # Verify amounts are Decimal
    for row in result.rows:
        assert isinstance(row["amount"], Decimal)
        assert row["amount"] > 0


def test_validate_multi_row_collects_all_errors() -> None:
    """All rows fail → all three errors are collected (collect-then-report)."""
    rows = [
        {"dept_id": "XXXX", "account_code": "SC001", "amount": "100"},
        {"dept_id": "4023", "account_code": "OP001", "amount": "100"},
        {"dept_id": "4023", "account_code": "SC001", "amount": "0"},
    ]
    result = _VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_CODES,
        shared_cost_codes=_SHARED_CODES,
    )

    assert result.valid is False
    assert len(result.errors) == 3
    codes = {e.code for e in result.errors}
    assert codes == {"SHARED_001", "SHARED_002", "SHARED_003"}
