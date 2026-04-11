# Spec: infra/csv_io

Module: `backend/src/app/infra/csv_io/__init__.py` | Tests: `backend/tests/unit/infra/test_csv_io.py` | FRs: FR-008, FR-024, FR-027

## Exports

```python
def parse_dicts(content: bytes) -> list[dict[str, str]]:
    """Parse UTF-8 encoded CSV bytes into a list of row dicts.

    Uses stdlib csv.DictReader. The first row is the header. Empty rows are skipped.
    Rejects non-UTF-8 encoded content.

    Args:
        content (bytes): Raw CSV file bytes. Must be UTF-8 encoded (no BOM, no Big5).

    Returns:
        list[dict[str, str]]: One dict per data row; all values are strings.

    Raises:
        InfraError: code='SYS_002' if content cannot be decoded as UTF-8.
        InfraError: code='SYS_002' if CSV is malformed (e.g. inconsistent column count).
    """
```

## Imports

- `csv`: `DictReader`
- `io`: `StringIO`
- `app.core.errors`: `InfraError`

## Side Effects

None.

## Gotchas

- Decode with `content.decode("utf-8")` — do NOT use `"utf-8-sig"` (which silently strips BOM). If Big5 test fixtures are needed, they must be rejected with `InfraError`, not silently misread.
- All values in the returned dicts are strings (`csv.DictReader` default). Callers apply `clean_cell` before type coercion.
- If the CSV has a BOM (`\xef\xbb\xbf` prefix), the decoded string will contain the BOM in the first header key. The spec requires rejecting non-UTF-8; a UTF-8 BOM is technically valid UTF-8, so accept it by stripping the BOM (`content.lstrip(b'\xef\xbb\xbf')`).

## Tests

1. `test_parse_valid_csv` — two-column CSV with header + 3 rows; returns 3 dicts.
2. `test_empty_rows_skipped` — CSV with blank line between rows; blank not in output.
3. `test_non_utf8_raises_infra_error` — Big5-encoded bytes; assert `InfraError("SYS_002", ...)`.
4. `test_all_values_are_strings` — numeric cell in CSV; `type(row["amount"]) == str`.
5. `test_empty_csv_returns_empty_list` — header-only CSV; returns `[]`.

## Constraints

None.
