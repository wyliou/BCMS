"""Unit tests for :mod:`app.domain.accounts.validator`."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.accounts.validator import ActualsRowValidator, validate


def _make_lookups(code_map: dict[str, UUID]) -> tuple[dict[str, UUID], set[str]]:
    """Return default lookup maps used across the tests."""
    return code_map, {"5101", "5102", "5103"}


def test_validate_all_valid_rows() -> None:
    """Every valid row passes → ``valid=True`` and cleaned rows emitted."""
    org_id = uuid4()
    org_map, account_set = _make_lookups({"4000": org_id})
    rows = [
        {"org_unit_code": "4000", "account_code": "5101", "amount": "100.00"},
        {"org_unit_code": "4000", "account_code": "5102", "amount": "250"},
    ]
    result = validate(rows, org_unit_codes=org_map, account_codes=account_set)
    assert result.valid is True
    assert len(result.rows) == 2
    assert result.rows[0]["amount"] == Decimal("100.00")
    assert result.rows[1]["amount"] == Decimal("250.00")
    assert result.rows[0]["org_unit_id"] == org_id


def test_validate_unknown_org_unit() -> None:
    """Unknown ``org_unit_code`` produces a row error on column ``org_unit_code``."""
    org_map, account_set = _make_lookups({"4000": uuid4()})
    rows = [
        {"org_unit_code": "9999", "account_code": "5101", "amount": "100"},
    ]
    result = validate(rows, org_unit_codes=org_map, account_codes=account_set)
    assert result.valid is False
    assert len(result.errors) == 1
    err = result.errors[0]
    assert err.row == 1
    assert err.column == "org_unit_code"
    assert err.code == "ACCOUNT_002"
    assert "9999" in err.reason


def test_validate_unknown_account_code() -> None:
    """Unknown ``account_code`` produces a row error on column ``account_code``."""
    org_map, account_set = _make_lookups({"4000": uuid4()})
    rows = [
        {"org_unit_code": "4000", "account_code": "9999", "amount": "100"},
    ]
    result = validate(rows, org_unit_codes=org_map, account_codes=account_set)
    assert result.valid is False
    err = result.errors[0]
    assert err.column == "account_code"
    assert err.code == "ACCOUNT_002"


def test_validate_bad_amount_format() -> None:
    """Non-numeric amount → row error on column ``amount``."""
    org_map, account_set = _make_lookups({"4000": uuid4()})
    rows = [
        {"org_unit_code": "4000", "account_code": "5101", "amount": "abc"},
    ]
    result = validate(rows, org_unit_codes=org_map, account_codes=account_set)
    assert result.valid is False
    err = result.errors[0]
    assert err.column == "amount"
    assert err.code == "ACCOUNT_002"


def test_validate_negative_amount() -> None:
    """Negative amount rejected (FR-008 parse_amount behaviour)."""
    org_map, account_set = _make_lookups({"4000": uuid4()})
    rows = [
        {"org_unit_code": "4000", "account_code": "5101", "amount": "-5"},
    ]
    result = validate(rows, org_unit_codes=org_map, account_codes=account_set)
    assert result.valid is False
    assert result.errors[0].column == "amount"


def test_validate_zero_allowed() -> None:
    """Zero amount accepted (FR-008 uses ``allow_zero=True``)."""
    org_id = uuid4()
    org_map, account_set = _make_lookups({"4000": org_id})
    rows = [
        {"org_unit_code": "4000", "account_code": "5101", "amount": 0},
    ]
    result = validate(rows, org_unit_codes=org_map, account_codes=account_set)
    assert result.valid is True
    assert result.rows[0]["amount"] == Decimal("0.00")


def test_validate_mixed_rows_row_numbers_preserved() -> None:
    """Mixed valid + invalid rows — errors reference 1-based row numbers."""
    org_map, account_set = _make_lookups({"4000": uuid4()})
    rows = [
        {"org_unit_code": "4000", "account_code": "5101", "amount": "10"},
        {"org_unit_code": "9999", "account_code": "5101", "amount": "10"},
        {"org_unit_code": "4000", "account_code": "5102", "amount": "abc"},
        {"org_unit_code": "4000", "account_code": "5103", "amount": "20"},
    ]
    result = validate(rows, org_unit_codes=org_map, account_codes=account_set)
    assert result.valid is False
    # Only the invalid rows produce errors, by 1-based row number.
    row_numbers = {e.row for e in result.errors}
    assert row_numbers == {2, 3}
    # On failure, rows is empty — the persisting transaction must never run.
    assert result.rows == []


def test_validate_empty_required_cells() -> None:
    """Empty org_unit_code / account_code both produce 'empty' errors."""
    org_map, account_set = _make_lookups({"4000": uuid4()})
    rows = [
        {"org_unit_code": "", "account_code": None, "amount": "10"},
    ]
    result = validate(rows, org_unit_codes=org_map, account_codes=account_set)
    assert result.valid is False
    columns = {e.column for e in result.errors}
    assert "org_unit_code" in columns
    assert "account_code" in columns


def test_class_instance_equivalent() -> None:
    """:class:`ActualsRowValidator` matches the module-level alias."""
    validator = ActualsRowValidator()
    org_map, account_set = _make_lookups({"4000": uuid4()})
    rows = [{"org_unit_code": "4000", "account_code": "5101", "amount": 5}]
    r1 = validator.validate(rows, org_unit_codes=org_map, account_codes=account_set)
    r2 = validate(rows, org_unit_codes=org_map, account_codes=account_set)
    assert r1.valid is True
    assert r2.valid is True
