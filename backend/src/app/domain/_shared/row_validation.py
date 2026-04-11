"""Collect-then-report row validation primitives (build-plan §5.3).

This module is the zero-dependency shared kernel used by every importer
(``domain/accounts``, ``domain/budget_uploads``, ``domain/personnel``,
``domain/shared_costs``). It owns:

* :class:`RowError` / :class:`ValidationResult` — the data shapes every
  validator hands back.
* :func:`clean_cell` — **CR-022** owner: the canonical whitespace /
  empty-string / numeric-header normalization helper. Every cell read from
  ``csv.DictReader`` or ``openpyxl`` MUST pass through this function
  before any comparison.
* :class:`AmountParseError` + :func:`parse_amount` — **CR-012** owner:
  the single money-parsing helper. Its ``allow_zero`` keyword encodes the
  per-FR business rule (``False`` for personnel/shared-cost, ``True`` for
  budget uploads and actuals). Callers wrap every invocation in
  ``try/except AmountParseError`` per **CR-021** and translate the caught
  exception into a :class:`RowError`.

The module intentionally has **no imports from ``app.*``** — it is a pure
stdlib utility so that ``core.errors`` can reference it via a
``TYPE_CHECKING`` forward declaration without producing a circular import
at module-load time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

__all__ = [
    "AmountParseError",
    "RowError",
    "ValidationResult",
    "clean_cell",
    "parse_amount",
]


_QUANTUM: Decimal = Decimal("0.01")


def _empty_rows() -> list[dict[str, Any]]:
    """Return a fresh empty list typed for :attr:`ValidationResult.rows`."""
    return []


def _empty_errors() -> list[RowError]:
    """Return a fresh empty list typed for :attr:`ValidationResult.errors`."""
    return []


@dataclass
class RowError:
    """A single row-level validation error from a collect-then-report validator.

    Attributes:
        row: 1-based row number from the source file.
        column: Column name where the error occurred, or ``None`` for a
            row-level (cross-column) error.
        code: Error code string (must appear in ``app.core.errors.ERROR_REGISTRY``).
        reason: Human-readable description of the specific failure.
    """

    row: int
    column: str | None
    code: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize the error into a JSON-friendly dict.

        Used by :class:`app.core.errors.BatchValidationError` to populate
        its ``details`` list when assembling the error envelope.

        Returns:
            dict[str, Any]: Mapping with keys ``row``, ``column``,
            ``code`` and ``reason``.
        """
        return {
            "row": self.row,
            "column": self.column,
            "code": self.code,
            "reason": self.reason,
        }


@dataclass
class ValidationResult:
    """Container returned by every ``*Validator.validate`` method.

    Attributes:
        rows: Parsed and cleaned row dicts. Callers should only read this
            list when :attr:`valid` is ``True``.
        errors: List of :class:`RowError` objects collected during
            validation. An empty list means the batch is valid.
    """

    rows: list[dict[str, Any]] = field(default_factory=_empty_rows)
    errors: list[RowError] = field(default_factory=_empty_errors)

    @property
    def valid(self) -> bool:
        """Return ``True`` iff no row errors were collected.

        Returns:
            bool: ``True`` when :attr:`errors` is empty.
        """
        return len(self.errors) == 0


def clean_cell(value: object | None) -> str | None:
    """Normalize a raw cell value from ``openpyxl`` or ``csv.DictReader``.

    Strips leading/trailing whitespace. Treats ``None`` and empty strings
    as ``None``. Converts non-string scalars (e.g. the ``int`` returned by
    openpyxl for a numeric header cell) to ``str`` first so downstream
    comparisons can always use a ``str``.

    Args:
        value: Raw cell value of any type.

    Returns:
        str | None: The stripped string, or ``None`` when the input was
        ``None`` or an empty/whitespace-only string.
    """
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    # Reason: openpyxl frequently returns int/float/Decimal for numeric
    # header cells. Stringify once so every caller deals in str.
    text = str(value).strip()
    return text or None


class AmountParseError(ValueError):
    """Raised by :func:`parse_amount` on an invalid money cell.

    This is a :class:`ValueError` subclass (NOT an :class:`AppError`) so
    it never leaks through the FastAPI exception handler. Callers catch
    it inside their row loop and translate it into a :class:`RowError`
    (per **CR-021**).

    Attributes:
        column: The column name the caller was parsing (defaults to
            ``"amount"``).
        code: The error code the caller will attach to the resulting
            :class:`RowError` (e.g. ``"UPLOAD_005"``, ``"ACCOUNT_002"``).
        reason: Human-readable explanation.
    """

    def __init__(
        self,
        reason: str,
        *,
        column: str = "amount",
        code: str | None = None,
    ) -> None:
        """Initialize the error with the caller-facing metadata.

        Args:
            reason: Human-readable reason.
            column: Column name (default ``"amount"``).
            code: Optional caller-supplied error code string.
        """
        super().__init__(reason)
        self.column = column
        self.code = code
        self.reason = reason


def parse_amount(value: object | None, *, allow_zero: bool) -> Decimal:
    """Parse a user-supplied cell into a quantized :class:`Decimal`.

    Accepted input types are ``int``, ``float``, ``str``, and
    :class:`Decimal`. ``None``, an empty string, non-numeric strings,
    negative values, and (optionally) zero all raise
    :class:`AmountParseError`. The result is always quantized to two
    decimal places using :data:`decimal.ROUND_HALF_EVEN` (banker's
    rounding) so storage is deterministic regardless of whether the
    source was a CSV string or an openpyxl float.

    Args:
        value: Raw cell value to parse.
        allow_zero: When ``False``, a parsed value of ``0`` raises
            :class:`AmountParseError`. Set ``True`` for actuals (FR-008)
            and budget uploads (FR-011). Set ``False`` for personnel
            (FR-024) and shared cost (FR-027).

    Returns:
        Decimal: ``Decimal(value).quantize(Decimal("0.01"))``.

    Raises:
        AmountParseError: On ``None`` input, a non-numeric value, a
            negative value, or zero when ``allow_zero=False``.
    """
    if value is None:
        raise AmountParseError("amount is empty")
    if isinstance(value, bool):
        # Reason: bool is an int subclass — reject early so True/False
        # never get silently coerced into Decimal("1")/Decimal("0").
        raise AmountParseError("amount must be numeric, got bool")

    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, int):
        decimal_value = Decimal(value)
    elif isinstance(value, float):
        # Reason: go via str to avoid binary-float artefacts
        # (Decimal(0.1) != Decimal("0.1")). openpyxl emits floats for
        # numeric cells so this branch is hot.
        decimal_value = Decimal(str(value))
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise AmountParseError("amount is empty")
        try:
            decimal_value = Decimal(stripped)
        except (InvalidOperation, ValueError) as exc:
            raise AmountParseError(f"amount is not numeric: {value!r}") from exc
    else:
        raise AmountParseError(f"amount has unsupported type: {type(value).__name__}")

    if not decimal_value.is_finite():
        raise AmountParseError(f"amount is not finite: {value!r}")

    if decimal_value < 0:
        raise AmountParseError(f"amount must be non-negative, got {decimal_value}")

    if decimal_value == 0 and not allow_zero:
        raise AmountParseError("amount must be strictly positive")

    try:
        quantized = decimal_value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
    except InvalidOperation as exc:  # pragma: no cover — defensive
        raise AmountParseError(f"amount overflow: {value!r}") from exc
    return quantized
