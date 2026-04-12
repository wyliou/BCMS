"""Unit tests for :class:`PersonnelImportValidator` (FR-024).

One test per error code (PERS_001..003) plus happy path and edge cases.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.domain.personnel.validator import PersonnelImportValidator

VALIDATOR = PersonnelImportValidator()

# ----------------------------------------------------------------- fixtures
_ORG_UNIT_A_ID = uuid4()
_ORG_UNIT_B_ID = uuid4()

_ORG_UNIT_CODES = {
    "4023": _ORG_UNIT_A_ID,
    "4024": _ORG_UNIT_B_ID,
}
_PERSONNEL_CODES = {"HR001", "HR002", "HR003"}


def _valid_rows() -> list[dict[str, object]]:
    """Return three valid rows for the standard fixtures."""
    return [
        {"dept_id": "4023", "account_code": "HR001", "amount": "1000"},
        {"dept_id": "4023", "account_code": "HR002", "amount": "2000.50"},
        {"dept_id": "4024", "account_code": "HR003", "amount": "500"},
    ]


# ================================================================ happy path
def test_validate_all_valid_rows() -> None:
    """Three valid rows → ValidationResult.valid is True, rows resolved."""
    result = VALIDATOR.validate(
        _valid_rows(),
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is True
    assert len(result.rows) == 3
    assert result.errors == []
    # Verify ids are resolved (not the raw code string).
    assert result.rows[0]["org_unit_id"] == _ORG_UNIT_A_ID
    assert result.rows[0]["account_code"] == "HR001"
    assert result.rows[0]["amount"] == Decimal("1000.00")


def test_validate_empty_rows_returns_valid() -> None:
    """Empty input → valid result with no rows and no errors."""
    result = VALIDATOR.validate(
        [],
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is True
    assert result.rows == []
    assert result.errors == []


# ================================================================ PERS_001
def test_validate_pers_001_unknown_dept_id() -> None:
    """Unknown dept_id → PERS_001 row error on correct row and column."""
    rows = [
        {"dept_id": "9999", "account_code": "HR001", "amount": "500"},
        {"dept_id": "4023", "account_code": "HR001", "amount": "500"},
    ]
    result = VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is False
    assert len(result.errors) == 1
    err = result.errors[0]
    assert err.code == "PERS_001"
    assert err.column == "dept_id"
    assert err.row == 1  # 1-based
    assert "9999" in err.reason


def test_validate_pers_001_dept_id_uuid_format_rejected() -> None:
    """A UUID-format dept_id not in the map raises PERS_001 (CR-018)."""
    rows = [{"dept_id": str(uuid4()), "account_code": "HR001", "amount": "100"}]
    result = VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is False
    assert result.errors[0].code == "PERS_001"


# ================================================================ PERS_002
def test_validate_pers_002_wrong_account_category() -> None:
    """Non-personnel account code → PERS_002 row error."""
    rows = [{"dept_id": "4023", "account_code": "OP001", "amount": "500"}]
    result = VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is False
    err = result.errors[0]
    assert err.code == "PERS_002"
    assert err.column == "account_code"
    assert err.row == 1


def test_validate_pers_002_empty_account_code() -> None:
    """Empty account_code → PERS_002 (clean_cell returns None → not in set)."""
    rows = [{"dept_id": "4023", "account_code": "   ", "amount": "500"}]
    result = VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is False
    assert result.errors[0].code == "PERS_002"


# ================================================================ PERS_003
def test_validate_pers_003_non_numeric_amount() -> None:
    """Non-numeric amount → PERS_003 with AmountParseError wrapped (CR-021)."""
    rows = [{"dept_id": "4023", "account_code": "HR001", "amount": "abc"}]
    result = VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is False
    err = result.errors[0]
    assert err.code == "PERS_003"
    assert err.column == "amount"
    assert err.row == 1


def test_validate_pers_003_zero_amount_rejected() -> None:
    """Zero amount rejected per CR-012 (allow_zero=False for personnel)."""
    rows = [{"dept_id": "4023", "account_code": "HR001", "amount": "0"}]
    result = VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is False
    err = result.errors[0]
    assert err.code == "PERS_003"
    assert err.column == "amount"
    # Verify reason mentions positivity constraint (CR-012).
    assert "positive" in err.reason.lower() or ">" in err.reason


def test_validate_pers_003_negative_amount() -> None:
    """Negative amount → PERS_003 row error."""
    rows = [{"dept_id": "4023", "account_code": "HR001", "amount": "-100"}]
    result = VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is False
    err = result.errors[0]
    assert err.code == "PERS_003"


def test_validate_pers_003_bad_format() -> None:
    """Malformed amount string → PERS_003 (AmountParseError caught, CR-021)."""
    rows = [{"dept_id": "4023", "account_code": "HR001", "amount": "1,000"}]
    result = VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    # Comma-formatted numbers are not parseable.
    assert result.valid is False
    assert result.errors[0].code == "PERS_003"


# ================================================================ mixed
def test_validate_mixed_valid_and_invalid_row_numbers() -> None:
    """Mixed rows: only invalid rows in errors; row numbers are 1-based."""
    rows = [
        {"dept_id": "4023", "account_code": "HR001", "amount": "500"},  # valid → row 1
        {"dept_id": "9999", "account_code": "HR001", "amount": "100"},  # PERS_001 → row 2
        {"dept_id": "4023", "account_code": "HR002", "amount": "200"},  # valid → row 3
    ]
    result = VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is False
    assert len(result.errors) == 1
    assert result.errors[0].row == 2
    assert result.errors[0].code == "PERS_001"
    # When errors exist, clean_rows is empty per collect-then-report.
    assert result.rows == []


# ================================================================ CR-022 (clean_cell)
def test_validate_clean_cell_applied_to_dept_id() -> None:
    """Leading/trailing whitespace on dept_id is tolerated (CR-022)."""
    rows = [{"dept_id": "  4023  ", "account_code": "HR001", "amount": "500"}]
    result = VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is True
    assert result.rows[0]["org_unit_id"] == _ORG_UNIT_A_ID


def test_validate_clean_cell_applied_to_account_code() -> None:
    """Whitespace on account_code is stripped before lookup (CR-022)."""
    rows = [{"dept_id": "4023", "account_code": " HR001 ", "amount": "500"}]
    result = VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is True


# ================================================================ CR-019 (header normalization)
def test_validate_chinese_headers_accepted() -> None:
    """Chinese column headers are normalized to canonical names (CR-019)."""
    rows = [{"部門id": "4023", "會科代碼": "HR001", "金額": "500"}]
    result = VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is True
    assert len(result.rows) == 1


def test_validate_unknown_headers_returns_batch_error() -> None:
    """Completely unknown headers → single batch-level error before row validation."""
    rows = [{"foo": "4023", "bar": "HR001", "baz": "500"}]
    result = VALIDATOR.validate(
        rows,
        org_unit_codes=_ORG_UNIT_CODES,
        personnel_codes=_PERSONNEL_CODES,
    )
    assert result.valid is False
    assert len(result.errors) >= 1
    # Batch error has row=0.
    assert result.errors[0].row == 0
