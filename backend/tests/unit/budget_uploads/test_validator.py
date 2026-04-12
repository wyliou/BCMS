"""Unit tests for :class:`BudgetUploadValidator` (FR-011, CR-004)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.core.errors import AppError
from app.domain.budget_uploads import validator as validator_module
from app.domain.budget_uploads.validator import BudgetUploadValidator
from tests.unit.budget_uploads.conftest import build_valid_workbook

OPERATIONAL = {"5101", "5102", "5103"}


@dataclass
class _StubSettings:
    """Tiny stand-in for :class:`app.config.Settings`.

    Attributes:
        max_upload_bytes: Size limit injected into the validator.
        max_upload_rows: Row-count limit injected into the validator.
    """

    max_upload_bytes: int = 10 * 1024 * 1024
    max_upload_rows: int = 5000


def _patch_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    max_upload_bytes: int | None = None,
    max_upload_rows: int | None = None,
) -> None:
    """Patch ``validator_module.get_settings`` to return a stub.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        max_upload_bytes: Optional override for the size limit.
        max_upload_rows: Optional override for the row-count limit.
    """
    stub = _StubSettings()
    if max_upload_bytes is not None:
        stub.max_upload_bytes = max_upload_bytes
    if max_upload_rows is not None:
        stub.max_upload_rows = max_upload_rows

    def _fake_get_settings() -> _StubSettings:
        return stub

    monkeypatch.setattr(validator_module, "get_settings", _fake_get_settings)


# --------------------------------------------------------------------- happy
def test_validate_happy_path() -> None:
    """A valid workbook with three rows passes all checks cleanly."""
    content = build_valid_workbook(
        dept_code="4023",
        rows=[
            ("5101", "Office Supplies", "1200", 1500),
            ("5102", "Travel", "500", 800),
            ("5103", "Training", "0", 0),
        ],
    )
    validator = BudgetUploadValidator()

    result = validator.validate(
        content,
        expected_dept_code="4023",
        operational_codes=OPERATIONAL,
    )

    assert result.valid is True
    assert len(result.rows) == 3
    codes = {row["account_code"] for row in result.rows}
    assert codes == OPERATIONAL


# ----------------------------------------------------------- UPLOAD_001 size
def test_validate_upload_001_size_exceeds_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Content larger than ``max_upload_bytes`` raises ``UPLOAD_001``."""
    _patch_settings(monkeypatch, max_upload_bytes=16)
    validator = BudgetUploadValidator()
    huge = b"\x00" * 32

    with pytest.raises(AppError) as excinfo:
        validator.validate(
            huge,
            expected_dept_code="4023",
            operational_codes=OPERATIONAL,
        )
    assert excinfo.value.code == "UPLOAD_001"


# ----------------------------------------------------------- UPLOAD_002 rows
def test_validate_upload_002_row_count_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """More than ``max_upload_rows`` data rows raises ``UPLOAD_002``."""
    _patch_settings(monkeypatch, max_upload_rows=2)
    content = build_valid_workbook(
        dept_code="4023",
        rows=[("5101", "A", "0", 1), ("5102", "B", "0", 2), ("5103", "C", "0", 3)],
    )

    validator = BudgetUploadValidator()
    with pytest.raises(AppError) as excinfo:
        validator.validate(
            content,
            expected_dept_code="4023",
            operational_codes=OPERATIONAL,
        )
    assert excinfo.value.code == "UPLOAD_002"


# ------------------------------------------------------------ UPLOAD_003
def test_validate_upload_003_dept_code_mismatch() -> None:
    """Dept code in header cell ``B2`` must equal the expected value."""
    content = build_valid_workbook(
        dept_code="4099",
        rows=[("5101", "A", "0", 100)],
    )
    validator = BudgetUploadValidator()

    with pytest.raises(AppError) as excinfo:
        validator.validate(
            content,
            expected_dept_code="4023",
            operational_codes=OPERATIONAL,
        )
    assert excinfo.value.code == "UPLOAD_003"


# ------------------------------------------------------------ UPLOAD_004
def test_validate_upload_004_empty_account_code_collected() -> None:
    """Empty account_code is collected as a row-level ``UPLOAD_004``."""
    content = build_valid_workbook(
        dept_code="4023",
        rows=[
            (None, "Blank", "0", 100),  # type: ignore[arg-type]
            ("5102", "Travel", "0", 200),
        ],
    )
    validator = BudgetUploadValidator()

    result = validator.validate(
        content,
        expected_dept_code="4023",
        operational_codes=OPERATIONAL,
    )

    assert result.valid is False
    assert any(err.code == "UPLOAD_004" and err.column == "account_code" for err in result.errors)


def test_validate_upload_004_non_operational_code_collected() -> None:
    """Account codes outside the operational set are flagged ``UPLOAD_004``."""
    content = build_valid_workbook(
        dept_code="4023",
        rows=[("7777", "Payroll", "0", 100)],
    )
    validator = BudgetUploadValidator()

    result = validator.validate(
        content,
        expected_dept_code="4023",
        operational_codes=OPERATIONAL,
    )

    assert result.valid is False
    assert any("not operational" in err.reason for err in result.errors)


def test_validate_upload_004_empty_budget_amount_collected() -> None:
    """Empty ``budget_amount`` cell yields row-level ``UPLOAD_004``."""
    content = build_valid_workbook(
        dept_code="4023",
        rows=[("5101", "Office", "0", None)],  # type: ignore[list-item]
    )
    validator = BudgetUploadValidator()

    result = validator.validate(
        content,
        expected_dept_code="4023",
        operational_codes=OPERATIONAL,
    )

    assert result.valid is False
    assert any(err.code == "UPLOAD_004" and err.column == "budget_amount" for err in result.errors)


# ------------------------------------------------------------ UPLOAD_005
def test_validate_upload_005_bad_amount_format() -> None:
    """Non-numeric amount yields ``UPLOAD_005``."""
    content = build_valid_workbook(
        dept_code="4023",
        rows=[("5101", "A", "0", "abc")],
    )
    validator = BudgetUploadValidator()

    result = validator.validate(
        content,
        expected_dept_code="4023",
        operational_codes=OPERATIONAL,
    )

    assert result.valid is False
    assert any(err.code == "UPLOAD_005" for err in result.errors)


# ------------------------------------------------------------ UPLOAD_006
def test_validate_upload_006_negative_amount() -> None:
    """Negative amount yields ``UPLOAD_006``."""
    content = build_valid_workbook(
        dept_code="4023",
        rows=[("5101", "A", "0", -1)],
    )
    validator = BudgetUploadValidator()

    result = validator.validate(
        content,
        expected_dept_code="4023",
        operational_codes=OPERATIONAL,
    )

    assert result.valid is False
    assert any(err.code == "UPLOAD_006" for err in result.errors)


# ------------------------------------------------------------ zero allowed
def test_validate_zero_amount_accepted() -> None:
    """Amount zero is valid for budget uploads (CR-012 / FR-011)."""
    content = build_valid_workbook(
        dept_code="4023",
        rows=[("5101", "A", "0", 0)],
    )
    validator = BudgetUploadValidator()

    result = validator.validate(
        content,
        expected_dept_code="4023",
        operational_codes=OPERATIONAL,
    )

    assert result.valid is True
    assert result.rows[0]["amount"] == 0


# ---------------------------------------------------- multiple row errors
def test_validate_collects_multiple_row_errors() -> None:
    """The validator collects every row-level error before returning."""
    content = build_valid_workbook(
        dept_code="4023",
        rows=[
            ("5101", "A", "0", "bad"),  # UPLOAD_005
            ("5102", "B", "0", -5),  # UPLOAD_006
            (None, "C", "0", 10),  # UPLOAD_004
        ],
    )
    validator = BudgetUploadValidator()

    result = validator.validate(
        content,
        expected_dept_code="4023",
        operational_codes=OPERATIONAL,
    )

    assert result.valid is False
    codes = {err.code for err in result.errors}
    assert codes == {"UPLOAD_004", "UPLOAD_005", "UPLOAD_006"}
