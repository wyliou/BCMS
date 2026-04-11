"""Unit tests for :mod:`app.domain._shared.row_validation` (§5.3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain._shared.row_validation import (
    AmountParseError,
    RowError,
    ValidationResult,
    clean_cell,
    parse_amount,
)


# ------------------------------------------------------------- clean_cell
def test_clean_cell_none_returns_none() -> None:
    """``clean_cell(None)`` returns ``None``."""
    assert clean_cell(None) is None


def test_clean_cell_empty_string_returns_none() -> None:
    """``clean_cell("")`` returns ``None``."""
    assert clean_cell("") is None


def test_clean_cell_whitespace_returns_none() -> None:
    """Whitespace-only strings normalize to ``None``."""
    assert clean_cell("   ") is None


def test_clean_cell_strips_whitespace() -> None:
    """Leading/trailing whitespace is stripped."""
    assert clean_cell("  hello  ") == "hello"


def test_clean_cell_int_input() -> None:
    """openpyxl numeric header cells are coerced to ``str``."""
    assert clean_cell(42) == "42"


def test_clean_cell_float_input() -> None:
    """Float inputs are coerced via ``str``."""
    assert clean_cell(1.5) == "1.5"


# ------------------------------------------------------------- parse_amount
def test_parse_amount_valid_string() -> None:
    """A numeric string is quantized to 2 places."""
    assert parse_amount("1234.5", allow_zero=True) == Decimal("1234.50")


def test_parse_amount_int_input() -> None:
    """Integer input is quantized."""
    assert parse_amount(100, allow_zero=False) == Decimal("100.00")


def test_parse_amount_float_input() -> None:
    """Float inputs round-trip via ``str`` to avoid binary artefacts."""
    assert parse_amount(1.5, allow_zero=True) == Decimal("1.50")


def test_parse_amount_decimal_input() -> None:
    """Decimal inputs are quantized but otherwise untouched."""
    assert parse_amount(Decimal("42.4"), allow_zero=True) == Decimal("42.40")


def test_parse_amount_zero_allow_zero_true() -> None:
    """``allow_zero=True`` accepts a zero value."""
    assert parse_amount(0, allow_zero=True) == Decimal("0.00")


def test_parse_amount_zero_allow_zero_false_raises() -> None:
    """``allow_zero=False`` rejects a zero value."""
    with pytest.raises(AmountParseError):
        parse_amount(0, allow_zero=False)


def test_parse_amount_negative_always_raises() -> None:
    """Negative values raise regardless of ``allow_zero``."""
    with pytest.raises(AmountParseError):
        parse_amount(-1, allow_zero=True)
    with pytest.raises(AmountParseError):
        parse_amount("-5.00", allow_zero=False)


def test_parse_amount_non_numeric_raises() -> None:
    """Non-numeric strings raise."""
    with pytest.raises(AmountParseError):
        parse_amount("abc", allow_zero=True)


def test_parse_amount_none_raises() -> None:
    """``None`` raises."""
    with pytest.raises(AmountParseError):
        parse_amount(None, allow_zero=True)


def test_parse_amount_bool_raises() -> None:
    """Booleans are rejected (avoid int-subclass coercion)."""
    with pytest.raises(AmountParseError):
        parse_amount(True, allow_zero=True)


def test_parse_amount_precision_quantized_half_even() -> None:
    """``"1.234"`` quantizes to ``1.23`` (ROUND_HALF_EVEN)."""
    assert parse_amount("1.234", allow_zero=True) == Decimal("1.23")


# ------------------------------------------------------------- RowError / ValidationResult
def test_row_error_to_dict_preserves_fields() -> None:
    """``RowError.to_dict()`` carries row, column, code, reason."""
    err = RowError(row=3, column="amount", code="ACCOUNT_002", reason="bad")
    assert err.to_dict() == {
        "row": 3,
        "column": "amount",
        "code": "ACCOUNT_002",
        "reason": "bad",
    }


def test_validation_result_valid_empty() -> None:
    """``valid`` is ``True`` only when ``errors`` is empty."""
    assert ValidationResult().valid is True


def test_validation_result_invalid_with_errors() -> None:
    """``valid`` is ``False`` when at least one error is present."""
    result = ValidationResult(
        rows=[],
        errors=[RowError(row=1, column=None, code="ACCOUNT_002", reason="x")],
    )
    assert result.valid is False
