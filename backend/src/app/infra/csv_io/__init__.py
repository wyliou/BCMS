"""CSV adapter — ``parse_dicts(bytes) -> list[dict[str, str]]``.

Only UTF-8 input is accepted. BOM-prefixed UTF-8 is tolerated (the BOM is
stripped before decoding). Any other encoding raises
:class:`~app.core.errors.InfraError` with code ``CSV_001``.
"""

from __future__ import annotations

import csv
from io import StringIO

from app.core.errors import InfraError

__all__ = ["parse_dicts"]


def parse_dicts(content: bytes) -> list[dict[str, str]]:
    """Parse UTF-8 encoded CSV bytes into a list of string dicts.

    The first non-empty row is treated as the header row. Empty rows (every
    field empty or whitespace) are skipped. All values are strings.

    Args:
        content: Raw CSV file bytes. Must be UTF-8.

    Returns:
        list[dict[str, str]]: One dict per data row. Empty list when the
        input contains only a header.

    Raises:
        InfraError: ``CSV_001`` if ``content`` cannot be decoded as UTF-8 or
            if the CSV is malformed (e.g. NUL bytes).
    """
    if not isinstance(content, (bytes, bytearray)):
        raise InfraError("CSV_001", "csv.parse_dicts requires bytes input")
    raw = bytes(content).lstrip(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InfraError("CSV_001", "CSV content is not valid UTF-8") from exc
    try:
        reader = csv.DictReader(StringIO(text))
        rows: list[dict[str, str]] = []
        for row in reader:
            if all((value is None or str(value).strip() == "") for value in row.values()):
                continue
            normalized: dict[str, str] = {}
            for key, value in row.items():
                if key is None:
                    continue
                normalized[str(key)] = "" if value is None else str(value)
            rows.append(normalized)
    except csv.Error as exc:
        raise InfraError("CSV_001", f"Malformed CSV: {exc}") from exc
    return rows
