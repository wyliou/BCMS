"""Budget upload workbook validation (FR-011, CR-004 owner for M4).

Implements the seven-step validation chain from
``specs/domain_budget_uploads.md``:

1. Size check on raw bytes (``UPLOAD_001``) — batch-level, raises
   immediately.
2. Row count check (``UPLOAD_002``) — batch-level, raises immediately.
3. Header dept code match (``UPLOAD_003``) — batch-level, raises
   immediately (cell ``B2`` on the ``header`` sheet built by the M3
   template builder).
4. Required cell non-empty (``UPLOAD_004``) — row-level, collected.
5. Amount format valid (``UPLOAD_005``) — row-level, collected.
6. Amount ≥ 0 (``UPLOAD_006``) — row-level, collected (zero is valid
   for budget uploads per CR-012 / FR-011).
7. Collect-then-report (``UPLOAD_007``) — the service layer raises
   :class:`BatchValidationError` when :attr:`ValidationResult.valid`
   is ``False``.

The validator itself does not know about :class:`BatchValidationError` —
it collects row-level errors and returns them to the service, which is
the single site that raises (keeps the validator pure and testable).

``account_code`` values are additionally checked against the caller-
supplied ``operational_codes`` set; rows referring to a non-operational
code are flagged as ``UPLOAD_004`` with a "not an operational code"
reason so operators see a single collected error per offending row.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from openpyxl import Workbook

from app.config import get_settings
from app.core.errors import AppError
from app.domain._shared.row_validation import (
    AmountParseError,
    RowError,
    ValidationResult,
    clean_cell,
    parse_amount,
)
from app.domain.templates.builder import ACCOUNT_COLUMNS
from app.infra.excel import open_workbook, read_rows

__all__ = ["BudgetUploadValidator"]


_HEADER_SHEET = "header"
_ACCOUNTS_SHEET = "accounts"

# Header sheet addresses from the M3 builder — dept code lives in B2.
_DEPT_CODE_CELL = "B2"


class BudgetUploadValidator:
    """Stateless validator for a budget upload workbook.

    The single public method :meth:`validate` consumes raw ``.xlsx`` bytes
    plus the two caller-supplied context values (expected department code
    and the set of operational account codes) and returns a
    :class:`ValidationResult`. Steps 1..3 are batch-level and raise
    :class:`AppError` directly; steps 4..6 are row-level and get collected
    into :attr:`ValidationResult.errors` for the service to translate
    into :class:`BatchValidationError` at step 7.
    """

    def validate(
        self,
        content: bytes,
        *,
        expected_dept_code: str,
        operational_codes: set[str],
    ) -> ValidationResult:
        """Run the full validation chain against ``content``.

        Args:
            content: Raw ``.xlsx`` bytes of the upload.
            expected_dept_code: The org unit's ``code`` value — must
                match the ``B2`` cell of the workbook's ``header`` sheet.
            operational_codes: Set of valid account code strings
                (CR-020) — any row referring to a code outside this set
                is collected as an ``UPLOAD_004`` row error.

        Returns:
            ValidationResult: ``rows`` is non-empty only when
                :attr:`ValidationResult.valid` is ``True``. Each row dict
                is ``{"row": int, "account_code": str, "amount": Decimal}``.

        Raises:
            AppError: ``UPLOAD_001`` (size), ``UPLOAD_002`` (row count),
                or ``UPLOAD_003`` (dept code mismatch) — batch-level.
        """
        settings = get_settings()

        # --- Step A: size check (batch-level) --------------------------
        if len(content) > settings.max_upload_bytes:
            raise AppError(
                "UPLOAD_001",
                f"File size {len(content)} exceeds {settings.max_upload_bytes} bytes",
            )

        # --- Step B: parse workbook ------------------------------------
        workbook: Workbook = open_workbook(content)

        # --- Step C: dept code header cell (batch-level) ---------------
        dept_value = self._read_dept_code(workbook)
        cleaned_dept = clean_cell(dept_value)
        cleaned_expected = clean_cell(expected_dept_code)
        if cleaned_dept != cleaned_expected:
            raise AppError(
                "UPLOAD_003",
                f"Dept code {cleaned_dept!r} does not match expected " f"{cleaned_expected!r}",
            )

        # --- Step D: row count check (batch-level) ---------------------
        raw_rows = read_rows(workbook, sheet_name=_ACCOUNTS_SHEET)
        if len(raw_rows) > settings.max_upload_rows:
            raise AppError(
                "UPLOAD_002",
                f"Row count {len(raw_rows)} exceeds {settings.max_upload_rows}",
            )

        # --- Steps E/F/G: per-row validation (collect-then-report) -----
        return self._validate_rows(
            raw_rows=raw_rows,
            operational_codes=operational_codes,
        )

    @staticmethod
    def _read_dept_code(workbook: Workbook) -> object | None:
        """Return the raw value of the header sheet's ``B2`` cell.

        Falls back to ``None`` when the ``header`` sheet is missing so
        the caller raises a uniform ``UPLOAD_003`` instead of a raw
        ``KeyError``.

        Args:
            workbook: The parsed openpyxl workbook.

        Returns:
            object | None: Raw cell value — ``str`` / ``int`` / ``None``.
        """
        if _HEADER_SHEET not in workbook.sheetnames:
            return None
        sheet = workbook[_HEADER_SHEET]
        return sheet[_DEPT_CODE_CELL].value

    def _validate_rows(
        self,
        *,
        raw_rows: list[dict[str, Any]],
        operational_codes: set[str],
    ) -> ValidationResult:
        """Validate each data row and return the collected result.

        Args:
            raw_rows: Row dicts from :func:`read_rows` — keyed by the
                ``accounts`` sheet header (``account_code``, ``amount``,
                and two passthrough columns).
            operational_codes: Valid account code set (CR-020).

        Returns:
            ValidationResult: Clean rows + collected row errors.
        """
        errors: list[RowError] = []
        clean_rows: list[dict[str, Any]] = []

        for index, raw in enumerate(raw_rows):
            # Reason: openpyxl rows are 1-based and the header is row 1,
            # so the first data row is row 2 in the source file.
            source_row = index + 2

            code_raw = raw.get("account_code")
            code_clean = clean_cell(code_raw)
            if code_clean is None:
                errors.append(
                    RowError(
                        row=source_row,
                        column="account_code",
                        code="UPLOAD_004",
                        reason="Required cell is empty",
                    )
                )
                continue

            if code_clean not in operational_codes:
                errors.append(
                    RowError(
                        row=source_row,
                        column="account_code",
                        code="UPLOAD_004",
                        reason=f"Account code {code_clean!r} is not operational",
                    )
                )
                continue

            amount_raw = raw.get("budget_amount")
            if amount_raw is None or (isinstance(amount_raw, str) and amount_raw.strip() == ""):
                errors.append(
                    RowError(
                        row=source_row,
                        column="budget_amount",
                        code="UPLOAD_004",
                        reason="Required cell is empty",
                    )
                )
                continue

            try:
                amount: Decimal = parse_amount(amount_raw, allow_zero=True)
            except AmountParseError as exc:
                # Reason: parse_amount raises a single error type that
                # covers both "unparseable" and "negative"; translate
                # based on the reason text into UPLOAD_005 vs UPLOAD_006.
                reason_text = str(exc)
                error_code = "UPLOAD_006" if "non-negative" in reason_text else "UPLOAD_005"
                errors.append(
                    RowError(
                        row=source_row,
                        column="budget_amount",
                        code=error_code,
                        reason=reason_text,
                    )
                )
                continue

            clean_rows.append(
                {
                    "row": source_row,
                    "account_code": code_clean,
                    "amount": amount,
                }
            )

        if errors:
            return ValidationResult(rows=[], errors=errors)
        return ValidationResult(rows=clean_rows, errors=[])


# Reason: exported here so the service can reference the column tuple
# without importing from the M3 builder module — keeps budget_uploads
# decoupled from the template-builder internals.
_EXPECTED_ACCOUNT_COLUMNS: tuple[str, ...] = ACCOUNT_COLUMNS

# Type hint the validator rows payload carries so the service can
# construct BudgetLine rows without re-deriving the dict shape. Each
# row is: {"row": int, "account_code": str, "amount": Decimal}. The
# service also joins "account_code" → AccountCode.id via a lookup map.
_ValidationRow = dict[str, int | str | Decimal | UUID]
