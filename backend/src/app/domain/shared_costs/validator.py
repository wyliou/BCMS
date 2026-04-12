"""Shared cost import validation (FR-027, CR-004 owner for M6).

Implements the collect-then-report row validation for shared cost imports:

1. Header normalization (CR-019) — normalize incoming headers via an
   allow-list; raise batch-level ``SHARED_004`` for unknown headers.
2. Per-row validation (collect-then-report):
   - SHARED_001: ``dept_id`` not found in org tree (CR-018).
   - SHARED_002: ``account_code`` not in ``shared_cost`` category (CR-020).
   - SHARED_003: ``amount`` invalid / zero / negative (CR-012, CR-021).

The validator is stateless — it takes pre-resolved lookup maps as arguments
and returns a :class:`ValidationResult`. The service layer raises
:class:`BatchValidationError` when :attr:`ValidationResult.valid` is ``False``
(CR-004). The validator itself never raises ``BatchValidationError``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.errors import BatchValidationError
from app.domain._shared.row_validation import (
    AmountParseError,
    RowError,
    ValidationResult,
    clean_cell,
    parse_amount,
)

__all__ = ["SharedCostImportValidator", "HEADER_ALLOW_LIST"]


# CR-019: header normalization allow-list (same as personnel).
HEADER_ALLOW_LIST: dict[str, str] = {
    "dept_id": "dept_id",
    "部門id": "dept_id",
    "org_unit_code": "dept_id",
    "account_code": "account_code",
    "會科代碼": "account_code",
    "amount": "amount",
    "金額": "amount",
}

_REQUIRED_NORMALIZED: frozenset[str] = frozenset({"dept_id", "account_code", "amount"})


class SharedCostImportValidator:
    """Stateless validator for shared cost import rows.

    The single public method :meth:`validate` checks each row for three
    error types (SHARED_001, SHARED_002, SHARED_003) using the caller-
    supplied org-unit and account-code maps, and returns a collected
    :class:`ValidationResult`. Callers should normalize headers *before*
    passing rows here (the service does this via :func:`_normalize_headers`).
    """

    def validate(
        self,
        rows: list[dict[str, Any]],
        *,
        org_unit_codes: dict[str, UUID],
        shared_cost_codes: set[str],
    ) -> ValidationResult:
        """Validate rows from a parsed shared cost import file.

        Checks dept_id in org tree (SHARED_001), account_code in shared_cost
        category (SHARED_002), amount > 0 (SHARED_003). Collects all RowErrors.

        Args:
            rows: Parsed rows from ``infra.tabular.parse_table`` with
                headers already normalized via the HEADER_ALLOW_LIST.
            org_unit_codes: Map of ``org_unit.code`` → UUID from
                ``org_unit_code_to_id_map``.
            shared_cost_codes: Set of account codes in
                ``AccountCategory.shared_cost``.

        Returns:
            ValidationResult: ``.valid`` is ``True`` only if errors list
            is empty. ``.rows`` carries cleaned row dicts when valid:
            ``{"row": int, "dept_id": str, "org_unit_id": UUID,
            "account_code": str, "amount": Decimal}``.
        """
        errors: list[RowError] = []
        clean_rows: list[dict[str, Any]] = []

        for index, raw in enumerate(rows):
            # Reason: row numbers are 1-based; header is row 1; first data row is 2.
            source_row = index + 2

            # --- SHARED_001: dept_id check (CR-018) ----------------------
            raw_dept = raw.get("dept_id")
            dept_clean = clean_cell(raw_dept)
            if dept_clean is None or dept_clean not in org_unit_codes:
                errors.append(
                    RowError(
                        row=source_row,
                        column="dept_id",
                        code="SHARED_001",
                        reason=f"Unknown dept_id: {dept_clean!r}",
                    )
                )
                continue

            org_unit_id = org_unit_codes[dept_clean]

            # --- SHARED_002: account_code category check (CR-020) --------
            raw_code = raw.get("account_code")
            code_clean = clean_cell(raw_code)
            if code_clean is None or code_clean not in shared_cost_codes:
                errors.append(
                    RowError(
                        row=source_row,
                        column="account_code",
                        code="SHARED_002",
                        reason="Account code is not in shared_cost category",
                    )
                )
                continue

            # --- SHARED_003: amount > 0 (CR-012, CR-021) -----------------
            raw_amount = raw.get("amount")
            try:
                # CR-012: allow_zero=False for shared cost
                amount: Decimal = parse_amount(raw_amount, allow_zero=False)
            except AmountParseError as exc:
                # CR-021: catch per row, translate to RowError
                reason = str(exc)
                # Reason: parse_amount raises "amount must be strictly positive"
                # for zero values; surface this so the spec text "Amount must be > 0"
                # matches.
                if "strictly positive" in reason:
                    reason = "Amount must be > 0"
                errors.append(
                    RowError(
                        row=source_row,
                        column="amount",
                        code="SHARED_003",
                        reason=reason,
                    )
                )
                continue

            clean_rows.append(
                {
                    "row": source_row,
                    "dept_id": dept_clean,
                    "org_unit_id": org_unit_id,
                    "account_code": code_clean,
                    "amount": amount,
                }
            )

        if errors:
            return ValidationResult(rows=[], errors=errors)
        return ValidationResult(rows=clean_rows, errors=[])


def normalize_headers(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remap incoming row keys to canonical names via HEADER_ALLOW_LIST.

    Raises ``BatchValidationError(SHARED_004)`` if any key is unrecognised
    (batch-level error per CR-019, raised before row-level validation).

    Args:
        rows: Raw rows from ``parse_table``; keys are original header strings.

    Returns:
        list[dict[str, Any]]: Rows with keys remapped to canonical names.

    Raises:
        BatchValidationError: ``SHARED_004`` when an unknown header is found.
    """
    if not rows:
        return rows

    # Reason: inspect first row keys to detect unknown headers; all rows
    # will have the same keys since parse_table yields dicts from a uniform header.
    unknown: list[str] = []
    for raw_key in rows[0]:
        normalized_key = clean_cell(raw_key)
        if normalized_key is None:
            continue
        canonical = HEADER_ALLOW_LIST.get(normalized_key.lower())
        if canonical is None:
            unknown.append(raw_key)

    if unknown:
        raise BatchValidationError(
            "SHARED_004",
            message=f"Unknown column headers: {unknown!r}",
        )

    normalized: list[dict[str, Any]] = []
    for raw_row in rows:
        new_row: dict[str, Any] = {}
        for raw_key, value in raw_row.items():
            key_clean = clean_cell(raw_key)
            if key_clean is None:
                continue
            canonical = HEADER_ALLOW_LIST.get(key_clean.lower())
            if canonical is not None:
                new_row[canonical] = value
        normalized.append(new_row)
    return normalized
