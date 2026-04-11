# Spec: infra/excel

Module: `backend/src/app/infra/excel/__init__.py` | Tests: `backend/tests/unit/infra/test_excel.py` | FRs: FR-009 (template generation), FR-011 (upload parsing)

## Exports

```python
def open_workbook(content: bytes) -> Workbook:
    """Open an openpyxl Workbook from raw bytes.

    Args:
        content (bytes): Raw .xlsx file content.

    Returns:
        Workbook: openpyxl Workbook object (read_only=False for write access).

    Raises:
        InfraError: code='SYS_002' if content is not valid XLSX.
    """

def read_rows(workbook: Workbook, sheet_name: str | None = None) -> list[dict[str, object]]:
    """Read all non-empty rows from the first (or named) worksheet as dicts.

    The first row is treated as the header. Each subsequent row becomes a dict
    keyed by header values. Empty rows (all cells None or '') are skipped.

    Args:
        workbook (Workbook): openpyxl Workbook (from open_workbook).
        sheet_name (str | None): Worksheet name. If None, uses the active sheet.

    Returns:
        list[dict[str, object]]: One dict per non-header row; keys are header strings,
            values are raw cell values (str, int, float, datetime, or None).

    Raises:
        InfraError: code='SYS_002' if sheet_name is specified but not found.
    """

def write_workbook(workbook: Workbook, rows: list[dict[str, object]], sheet_name: str = "Sheet1") -> None:
    """Write rows to the named (or first) worksheet of an existing Workbook.

    Clears existing content before writing. First row is derived from dict keys.

    Args:
        workbook (Workbook): Workbook to write into (mutated in-place).
        rows (list[dict[str, object]]): Rows to write; all dicts must have identical keys.
        sheet_name (str): Target worksheet name. Created if absent. Defaults to 'Sheet1'.
    """

def workbook_to_bytes(workbook: Workbook) -> bytes:
    """Serialize a Workbook to raw XLSX bytes without writing to disk.

    Args:
        workbook (Workbook): openpyxl Workbook.

    Returns:
        bytes: XLSX file content suitable for storage or HTTP response.
    """
```

## Imports

| Module | Symbols |
|---|---|
| `openpyxl` | `Workbook`, `load_workbook` |
| `io` | `BytesIO` |
| `app.core.errors` | `InfraError` |

## Side Effects

None (pure I/O helpers; no network, no DB, no filesystem access).

## Gotchas

- `load_workbook(BytesIO(content))` is the correct pattern for in-memory parsing (no temp file).
- `read_rows` must handle cells where `cell.value` is an `int` or `float` (openpyxl numeric detection) — callers receive raw values; `clean_cell` in `domain/_shared/row_validation` normalizes them.
- `workbook_to_bytes` uses `BytesIO` as the save target: `wb.save(buf); return buf.getvalue()`.
- All openpyxl operations are synchronous and CPU-bound. Callers that need async behavior (domain services) must wrap calls in `run_in_threadpool`. This module itself is synchronous.
- `write_workbook` must create the worksheet if `sheet_name` does not exist; if it does exist, clear it before writing.

## Tests

1. `test_open_workbook_valid_xlsx` — build a minimal `Workbook`, save to bytes, `open_workbook` succeeds.
2. `test_open_workbook_invalid_bytes_raises` — pass random bytes; assert `InfraError("SYS_002", ...)`.
3. `test_read_rows_returns_dicts` — workbook with header row + 2 data rows; `read_rows` returns 2 dicts with correct keys.
4. `test_read_rows_skips_empty_rows` — insert a blank row between two data rows; assert blank is not in output.
5. `test_write_then_read_round_trip` — `write_workbook` then `read_rows` returns same data.
6. `test_workbook_to_bytes_is_valid_xlsx` — bytes can be reopened by `open_workbook` without error.
7. `test_read_rows_named_sheet_not_found_raises` — `sheet_name="NoSuch"` raises `InfraError`.

## Constraints

None.
