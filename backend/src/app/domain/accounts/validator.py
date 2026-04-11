"""Collect-then-report validator for the actuals import (FR-008).

The validator owns the row loop for :meth:`AccountService.import_actuals`
and is called **before** any DB write (CR-004). It accepts the parsed
rows from :func:`app.infra.tabular.parse_table` along with two lookup
structures (the org-unit code→id map from ``domain._shared.queries`` and
the set of valid account codes from :class:`AccountService`) and returns
a :class:`ValidationResult` with one :class:`RowError` per invalid row.

Every error produced here carries ``code="ACCOUNT_002"`` per the spec;
the column attribute identifies which field tripped the validation so
the front-end can highlight it (CR-021).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.domain._shared.row_validation import (
    AmountParseError,
    RowError,
    ValidationResult,
    clean_cell,
    parse_amount,
)

__all__ = ["ActualsRowValidator", "validate"]


_COLUMN_ORG_UNIT: str = "org_unit_code"
_COLUMN_ACCOUNT: str = "account_code"
_COLUMN_AMOUNT: str = "amount"
_ERROR_CODE: str = "ACCOUNT_002"


def _lookup_cell(row: dict[str, Any], *candidates: str) -> Any:
    """Return the first present cell value among ``candidates``.

    The ``infra.tabular`` adapter preserves header casing; the importer
    spec says headers are matched case-insensitively after
    :func:`clean_cell` + ``.lower()``. We still tolerate any casing by
    checking all provided aliases.

    Args:
        row: Parsed row dict from ``infra.tabular``.
        *candidates: Candidate header names in preferred order.

    Returns:
        object: The first non-missing value, or ``None`` if no alias is
        present.
    """
    for key in candidates:
        if key in row:
            return row[key]
    return None


class ActualsRowValidator:
    """Collect-then-report validator for the actuals-import CSV/XLSX.

    The :meth:`validate` method is the single entry point used by
    :meth:`app.domain.accounts.service.AccountService.import_actuals`.
    Instances are stateless so callers may reuse a module-level
    singleton, or instantiate per call — both work.
    """

    def validate(
        self,
        rows: list[dict[str, Any]],
        *,
        org_unit_codes: dict[str, UUID],
        account_codes: set[str],
    ) -> ValidationResult:
        """Validate every row and collect all errors (CR-004).

        Args:
            rows: Parsed rows from :func:`app.infra.tabular.parse_table`.
                Keys follow the upstream file headers (already
                case-normalized to ``org_unit_code`` / ``account_code`` /
                ``amount`` by the service layer before calling).
            org_unit_codes: Map produced by
                :func:`app.domain._shared.queries.org_unit_code_to_id_map`.
            account_codes: Set of valid account-code strings from
                :meth:`AccountService.get_operational_codes_set` (or
                another category accessor). Unknown codes are rejected.

        Returns:
            ValidationResult: ``rows`` contains cleaned dicts with keys
            ``org_unit_code``, ``org_unit_id``, ``account_code``, and
            ``amount`` (Decimal). ``errors`` is empty iff every row
            passed. Callers must check ``.valid`` before persisting.
        """
        clean_rows: list[dict[str, Any]] = []
        errors: list[RowError] = []

        for index, raw in enumerate(rows, start=1):
            row_errors = self._validate_row(
                row_number=index,
                raw=raw,
                org_unit_codes=org_unit_codes,
                account_codes=account_codes,
                sink=clean_rows,
            )
            errors.extend(row_errors)

        return ValidationResult(
            rows=clean_rows if not errors else [],
            errors=errors,
        )

    def _validate_row(
        self,
        *,
        row_number: int,
        raw: dict[str, Any],
        org_unit_codes: dict[str, UUID],
        account_codes: set[str],
        sink: list[dict[str, Any]],
    ) -> list[RowError]:
        """Validate a single row and append the cleaned form on success.

        Args:
            row_number: 1-based row index.
            raw: Raw row dict from the parser.
            org_unit_codes: Valid org-unit code→id map.
            account_codes: Valid account-code set.
            sink: List to append cleaned rows to (only appended on full
                success to preserve CR-004 ordering).

        Returns:
            list[RowError]: Errors found in this row (empty on success).
        """
        errors: list[RowError] = []

        # --- org_unit_code ---------------------------------------------
        raw_org = _lookup_cell(
            raw,
            _COLUMN_ORG_UNIT,
            "dept_id",
            "ORG_UNIT_CODE",
            "DEPT_ID",
        )
        org_code = clean_cell(raw_org)
        if org_code is None:
            errors.append(
                RowError(
                    row=row_number,
                    column=_COLUMN_ORG_UNIT,
                    code=_ERROR_CODE,
                    reason="Required cell is empty",
                )
            )
            org_unit_id: UUID | None = None
        else:
            org_unit_id = org_unit_codes.get(org_code)
            if org_unit_id is None:
                errors.append(
                    RowError(
                        row=row_number,
                        column=_COLUMN_ORG_UNIT,
                        code=_ERROR_CODE,
                        reason=f"Unknown org unit code: {org_code}",
                    )
                )

        # --- account_code ---------------------------------------------
        raw_account = _lookup_cell(raw, _COLUMN_ACCOUNT, "ACCOUNT_CODE")
        account_code = clean_cell(raw_account)
        if account_code is None:
            errors.append(
                RowError(
                    row=row_number,
                    column=_COLUMN_ACCOUNT,
                    code=_ERROR_CODE,
                    reason="Required cell is empty",
                )
            )
        elif account_code not in account_codes:
            errors.append(
                RowError(
                    row=row_number,
                    column=_COLUMN_ACCOUNT,
                    code=_ERROR_CODE,
                    reason=f"Unknown account code: {account_code}",
                )
            )

        # --- amount ----------------------------------------------------
        raw_amount = _lookup_cell(raw, _COLUMN_AMOUNT, "AMOUNT")
        try:
            amount = parse_amount(raw_amount, allow_zero=True)
        except AmountParseError as exc:
            errors.append(
                RowError(
                    row=row_number,
                    column=_COLUMN_AMOUNT,
                    code=_ERROR_CODE,
                    reason=str(exc),
                )
            )
            amount = None  # type: ignore[assignment]

        if not errors:
            sink.append(
                {
                    "row": row_number,
                    "org_unit_code": org_code,
                    "org_unit_id": org_unit_id,
                    "account_code": account_code,
                    "amount": amount,
                }
            )
        return errors


# Module-level convenience — matches the spec export name.
_DEFAULT_VALIDATOR = ActualsRowValidator()


def validate(
    rows: list[dict[str, Any]],
    *,
    org_unit_codes: dict[str, UUID],
    account_codes: set[str],
) -> ValidationResult:
    """Validate ``rows`` using the module-level :class:`ActualsRowValidator`.

    This is the free-function alias documented in the spec exports.
    Internally it delegates to :meth:`ActualsRowValidator.validate`.

    Args:
        rows: Parsed rows from :func:`app.infra.tabular.parse_table`.
        org_unit_codes: Org-unit code → id map.
        account_codes: Set of valid account-code strings.

    Returns:
        ValidationResult: See :meth:`ActualsRowValidator.validate`.
    """
    return _DEFAULT_VALIDATOR.validate(
        rows,
        org_unit_codes=org_unit_codes,
        account_codes=account_codes,
    )
