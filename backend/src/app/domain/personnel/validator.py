"""Personnel import row validation (FR-024, CR-004 owner for M5).

Implements the collect-then-report validation chain for personnel budget
CSV/XLSX imports:

1. Header normalization (CR-019): normalizes headers via ``clean_cell`` +
   ``.lower()`` against an allow-list mapping Chinese/English variants.
2. Row-level validation (collected):
   - PERS_001: ``dept_id`` not in org_unit_codes map (CR-018).
   - PERS_002: ``account_code`` not in personnel_codes (CR-020).
   - PERS_003: ``amount`` ≤ 0, non-numeric, or empty (CR-012, CR-021).
3. Returns :class:`ValidationResult` with resolved id-keyed rows or errors.

The validator itself never raises :class:`BatchValidationError` — it
returns errors to the service, which is the single site that raises.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from app.domain._shared.row_validation import (
    AmountParseError,
    RowError,
    ValidationResult,
    clean_cell,
    parse_amount,
)

__all__ = ["PersonnelImportValidator"]


# CR-019: allow-list mapping raw header text → canonical column name.
_HEADER_MAP: dict[str, str] = {
    "dept_id": "dept_id",
    "部門id": "dept_id",
    "org_unit_code": "dept_id",
    "account_code": "account_code",
    "會科代碼": "account_code",
    "amount": "amount",
    "金額": "amount",
}

_REQUIRED_COLUMNS: frozenset[str] = frozenset({"dept_id", "account_code", "amount"})


def _normalize_headers(raw_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize header keys in each row using the CR-019 allow-list.

    Args:
        raw_rows: Raw rows from :func:`infra.tabular.parse_table`.

    Returns:
        tuple[list[dict[str, Any]], list[str]]: A tuple of
        ``(normalized_rows, unknown_headers)``. If any key from any row
        does not appear in the allow-list, it is collected in
        ``unknown_headers``. The caller decides whether to reject.
    """
    if not raw_rows:
        return [], []

    # Inspect headers from first row only — parse_table returns uniform keys.
    sample_keys = list(raw_rows[0].keys())
    col_map: dict[str, str] = {}
    unknown: list[str] = []

    for key in sample_keys:
        canonical = _HEADER_MAP.get(clean_cell(key) or "")
        if canonical is None:
            canonical = _HEADER_MAP.get((clean_cell(key) or "").lower())
        if canonical is None:
            unknown.append(str(key))
        else:
            col_map[key] = canonical

    normalized: list[dict[str, Any]] = []
    for row in raw_rows:
        new_row: dict[str, Any] = {}
        for old_key, value in row.items():
            mapped = col_map.get(old_key)
            if mapped is not None:
                new_row[mapped] = value
        normalized.append(new_row)

    return normalized, unknown


class PersonnelImportValidator:
    """Stateless collect-then-report validator for personnel budget imports.

    The single public method :meth:`validate` accepts parsed rows plus two
    caller-supplied context dicts/sets and returns a :class:`ValidationResult`.
    All checks are row-level and collected; nothing raises directly (CR-004).
    """

    def validate(
        self,
        rows: list[dict[str, Any]],
        *,
        org_unit_codes: dict[str, UUID],
        personnel_codes: set[str],
    ) -> ValidationResult:
        """Validate rows from a parsed personnel import file.

        Checks dept_id in org tree (PERS_001), account_code in personnel
        category (PERS_002), amount > 0 (PERS_003). Collects all RowErrors.
        Header normalization is applied before row iteration (CR-019).
        ``clean_cell`` is applied to every string (CR-022).
        ``parse_amount(..., allow_zero=False)`` enforces CR-012.

        Args:
            rows: Parsed rows from infra.tabular.parse_table.
            org_unit_codes: Map of org_unit.code -> UUID from
                org_unit_code_to_id_map (CR-018).
            personnel_codes: Set of account codes in
                AccountCategory.personnel (CR-020).

        Returns:
            ValidationResult: ``.valid`` is True only when errors list
            is empty. On success, each row dict contains
            ``{org_unit_id, account_code_id, amount}``.
        """
        if not rows:
            return ValidationResult(rows=[], errors=[])

        # --- CR-019: header normalization ----------------------------------
        normalized_rows, unknown_headers = _normalize_headers(rows)
        if unknown_headers:
            return ValidationResult(
                rows=[],
                errors=[
                    RowError(
                        row=0,
                        column=None,
                        code="PERS_004",
                        reason=f"Unknown column headers: {unknown_headers!r}",
                    )
                ],
            )

        # Verify required columns present in normalized rows.
        present: set[str] = set(normalized_rows[0].keys()) if normalized_rows else set()
        missing = _REQUIRED_COLUMNS - present
        if missing:
            return ValidationResult(
                rows=[],
                errors=[
                    RowError(
                        row=0,
                        column=None,
                        code="PERS_004",
                        reason=f"Missing required columns: {sorted(missing)!r}",
                    )
                ],
            )

        # --- CR-004: per-row validation (collect-then-report) -----------
        errors: list[RowError] = []
        clean_rows: list[dict[str, Any]] = []

        for index, raw in enumerate(normalized_rows):
            # Reason: row numbers are 1-based per spec §9 requirement.
            source_row = index + 1

            # PERS_001: dept_id lookup (CR-018, CR-022)
            dept_raw = raw.get("dept_id")
            dept_clean = clean_cell(dept_raw)
            if dept_clean is None or dept_clean not in org_unit_codes:
                errors.append(
                    RowError(
                        row=source_row,
                        column="dept_id",
                        code="PERS_001",
                        reason=f"Unknown dept_id: {dept_clean!r}",
                    )
                )
                continue

            org_unit_id = org_unit_codes[dept_clean]

            # PERS_002: account_code must be in personnel category (CR-020, CR-022)
            code_raw = raw.get("account_code")
            code_clean = clean_cell(code_raw)
            if code_clean is None or code_clean not in personnel_codes:
                errors.append(
                    RowError(
                        row=source_row,
                        column="account_code",
                        code="PERS_002",
                        reason="Account code is not in personnel category",
                    )
                )
                continue

            # PERS_003: amount > 0 (CR-012, CR-021)
            amount_raw = raw.get("amount")
            try:
                # CR-012: allow_zero=False for personnel imports.
                amount: Decimal = parse_amount(amount_raw, allow_zero=False)
            except AmountParseError as exc:
                # CR-021: translate AmountParseError → RowError.
                errors.append(
                    RowError(
                        row=source_row,
                        column="amount",
                        code="PERS_003",
                        reason=str(exc),
                    )
                )
                continue

            clean_rows.append(
                {
                    "org_unit_id": org_unit_id,
                    "account_code": code_clean,
                    "amount": amount,
                }
            )

        if errors:
            return ValidationResult(rows=[], errors=errors)
        return ValidationResult(rows=clean_rows, errors=[])
