# Spec: infra/tabular

Module: `backend/src/app/infra/tabular.py` | Tests: `backend/tests/unit/infra/test_tabular.py` | FRs: FR-008, FR-024, FR-027

## Exports

```python
async def parse_table(filename: str, content: bytes) -> list[dict[str, object]]:
    """Dispatch CSV or XLSX content to the appropriate parser and return rows as dicts.

    File type is determined by the filename extension (case-insensitive).
    '.csv' → infra.csv_io.parse_dicts; '.xlsx' → infra.excel.open_workbook + read_rows.

    Args:
        filename (str): Original filename (used only for extension detection).
        content (bytes): Raw file bytes.

    Returns:
        list[dict[str, object]]: One dict per data row. CSV values are str; XLSX values
            are raw openpyxl types (str, int, float, datetime, None).

    Raises:
        InfraError: code='SYS_002' for unsupported extension or parse failure.
    """
```

## Imports

| Module | Symbols |
|---|---|
| `app.infra.csv_io` | `parse_dicts` |
| `app.infra.excel` | `open_workbook`, `read_rows` |
| `app.core.errors` | `InfraError` |
| `starlette.concurrency` | `run_in_threadpool` |

## Side Effects

None (delegates to `csv_io` and `excel`; wraps synchronous openpyxl calls in `run_in_threadpool`).

## Gotchas

- The extension check must be case-insensitive: `.CSV` and `.XLSX` are valid.
- **Domain importers MUST NOT import `infra.csv_io` or `infra.excel` directly** — this dispatcher is the single entry point (CR-024).
- `parse_dicts` is synchronous; when called from `parse_table`, wrap in `await run_in_threadpool(parse_dicts, content)` for consistency, even though CSV parsing is cheap.
- Unsupported extensions (`.xls`, `.pdf`, etc.) raise `InfraError("SYS_002", f"Unsupported file type: {ext}")`.

## Tests

1. `test_csv_file_dispatches_to_csv_io` — pass a `.csv` file; assert result matches `parse_dicts` output.
2. `test_xlsx_file_dispatches_to_excel` — pass a `.xlsx` file; assert result is list of dicts.
3. `test_case_insensitive_extension` — filename `"DATA.CSV"` dispatches correctly.
4. `test_unsupported_extension_raises` — filename `"data.xls"` raises `InfraError("SYS_002", ...)`.
5. `test_empty_csv_returns_empty_list` — header-only `.csv`; returns `[]`.

## Constraints

- **CR-024 Stage B check:** *"File parsing is delegated to `infra.tabular.parse_table(filename, content)`. Do not import `infra.csv_io` or `infra.excel` directly from a domain importer."*
