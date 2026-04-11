# Spec: domain/_shared/row_validation (§5.3)

**Batch:** 3
**Complexity:** Moderate

## Module & Test Paths

Module: `backend/src/app/domain/_shared/row_validation.py`
Tests: `backend/tests/unit/_shared/test_row_validation.py`
FRs: FR-008 (actuals import — `allow_zero=True`), FR-011 (budget upload — `allow_zero=True`), FR-024 (personnel — `allow_zero=False`), FR-027 (shared cost — `allow_zero=False`)

---

## Exports

```python
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class RowError:
    """A single row-level validation error from a collect-then-report validator.

    Attributes:
        row: 1-based row number from the source file.
        column: Column name where the error occurred, or None for row-level errors.
        code: Error code string (from ERROR_REGISTRY, e.g. 'ACCOUNT_002').
        reason: Human-readable description of the error.
    """
    row: int
    column: str | None
    code: str
    reason: str

    def to_dict(self) -> dict:
        """Serialize to dict for inclusion in BatchValidationError.details."""

@dataclass
class ValidationResult:
    """Container returned by every *Validator.validate method.

    Attributes:
        rows: Parsed, cleaned row dicts (only populated when valid).
        errors: List of RowError objects collected during validation.
    """
    rows: list[dict]
    errors: list[RowError]

    @property
    def valid(self) -> bool:
        """True iff errors list is empty."""
        return len(self.errors) == 0

def clean_cell(value: object | None) -> str | None:
    """Normalize a raw cell value from openpyxl or csv.DictReader.

    Strips leading/trailing whitespace. Treats None and empty string as None.
    Converts non-string types (e.g. int from openpyxl numeric header) to str first.

    Args:
        value: Raw cell value of any type.

    Returns:
        str | None: Stripped string or None if the input was empty/None.
    """

class AmountParseError(ValueError):
    """Raised by parse_amount on invalid input. NOT an AppError subclass."""

def parse_amount(value: object | None, *, allow_zero: bool) -> Decimal:
    """Parse and validate an amount value from a user-supplied cell.

    Accepts int, float, str, Decimal, or None as input.
    Normalizes to Decimal quantized to 0.01 (2 decimal places).

    Args:
        value: Raw cell value to parse.
        allow_zero: If False, a parsed value of 0 raises AmountParseError.
                    Set True for budget uploads (FR-011) and actuals (FR-008).
                    Set False for personnel (FR-024) and shared cost (FR-027).

    Returns:
        Decimal: Quantized Decimal(value).quantize(Decimal('0.01')).

    Raises:
        AmountParseError: On None input, non-numeric string, negative value,
                          or zero value when allow_zero=False.
    """
```

---

## `allow_zero` Semantics

| Caller module | FR | `allow_zero` | Reason |
|---|---|---|---|
| `domain/accounts` (actuals import) | FR-008 | `True` | Actuals may be zero (no data for a period) |
| `domain/budget_uploads` | FR-011 | `True` | Budget amounts may be zero (zero budget is valid) |
| `domain/personnel` | FR-024 | `False` | "金額為正數" — must be strictly > 0 |
| `domain/shared_costs` | FR-027 | `False` | "金額為正數" — must be strictly > 0 |

**`parse_amount` never returns a negative.** Negative values always raise `AmountParseError` regardless of `allow_zero`. The DB CHECK constraints (`amount >= 0` for `budget_lines`, `amount > 0` for `personnel_budget_lines` and `shared_cost_lines`) are a second line of defense.

---

## Imports

`decimal` (stdlib): `Decimal`, `InvalidOperation`
`typing` (stdlib): none (dataclasses used instead of Pydantic for zero-dependency shared utility)

This module has NO imports from `app.*`. It is a pure utility with zero domain dependencies.

---

## Tests

1. **`test_clean_cell_none_returns_none`** — `clean_cell(None)` returns `None`.
2. **`test_clean_cell_strips_whitespace`** — `clean_cell("  hello  ")` returns `"hello"`.
3. **`test_clean_cell_empty_string_returns_none`** — `clean_cell("")` returns `None`.
4. **`test_clean_cell_int_input`** — `clean_cell(42)` returns `"42"` (openpyxl numeric cell as column header).
5. **`test_parse_amount_valid_string`** — `parse_amount("1234.5", allow_zero=True)` returns `Decimal("1234.50")`.
6. **`test_parse_amount_int_input`** — `parse_amount(100, allow_zero=False)` returns `Decimal("100.00")`.
7. **`test_parse_amount_zero_allow_zero_true`** — `parse_amount(0, allow_zero=True)` returns `Decimal("0.00")`.
8. **`test_parse_amount_zero_allow_zero_false`** — `parse_amount(0, allow_zero=False)` raises `AmountParseError`.
9. **`test_parse_amount_negative_always_raises`** — `parse_amount(-1, allow_zero=True)` raises `AmountParseError`.
10. **`test_parse_amount_non_numeric_string`** — `parse_amount("abc", allow_zero=True)` raises `AmountParseError`.
11. **`test_parse_amount_none_raises`** — `parse_amount(None, allow_zero=True)` raises `AmountParseError`.
12. **`test_validation_result_valid_property`** — `ValidationResult(rows=[], errors=[])` has `.valid == True`.
13. **`test_validation_result_invalid_property`** — `ValidationResult(rows=[], errors=[RowError(...)])` has `.valid == False`.
14. **`test_row_error_to_dict`** — `RowError(row=3, column='amount', code='ACCOUNT_002', reason='bad').to_dict()` returns dict with all four keys.

---

## Constraints

CR-012 (owner: this module), CR-021, CR-022

**CR-012 — Personnel/shared_cost amount > 0; Budget amount ≥ 0**
*"This module calls `parse_amount(value, allow_zero=True)` for budget uploads (FR-011), `allow_zero=False` for personnel (FR-024) and shared_cost (FR-027). The DB CHECK constraints (`amount >= 0` for `budget_lines`, `amount > 0` for `personnel_budget_lines` and `shared_cost_lines`) are the second line of defense."*
The `allow_zero` parameter encodes this rule. `parse_amount` is the owner; callers pass the correct value.

**CR-021 — Robust amount parsing wrapped in try/except**
*"Every call to `parse_amount` is wrapped in `try/except AmountParseError`, and the caught exception becomes a `RowError(row=..., column='amount', code='UPLOAD_005|PERS_003|SHARED_003|ACCOUNT_002', reason=str(e))`."*
This constraint is on the callers, not this module. `parse_amount` raises `AmountParseError`; callers must catch it.

**CR-022 — `clean_cell` for every user-supplied string field**
*"Every cell read from openpyxl or `csv.DictReader` is passed through `clean_cell` before comparison. Direct `==` comparisons on raw cell values are forbidden."*
`clean_cell` is defined here; callers must invoke it. This module itself does not read cells.

---

## Gotchas

- `AmountParseError` is a `ValueError` subclass, NOT an `AppError` subclass. It must NOT propagate past a validator's row loop — callers catch it and wrap into `RowError`.
- `ValidationResult.rows` should contain the cleaned, parsed row dicts for use in the persisting transaction. Only populate when `valid == True` (caller pattern: check `valid` before accessing `rows`).
- `clean_cell` handles openpyxl returning `int` for numeric-looking column headers. This is a real-world edge case (e.g., a cell containing `2024` parsed as int).
- `Decimal.quantize(Decimal('0.01'))` uses `ROUND_HALF_EVEN` by default; this is acceptable for storage (exact representation). The `delta_pct` display rounding (CR-013, `ROUND_HALF_UP`) is separate and lives in `consolidation/report.py`.
