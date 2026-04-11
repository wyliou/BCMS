"""CSV/XLSX file dispatcher — single entry point for every importer (CR-024).

Domain importers MUST NOT reach into :mod:`app.infra.csv_io` or
:mod:`app.infra.excel` directly. They call :func:`parse_table` instead, which
dispatches to the correct parser based on the filename extension and wraps
synchronous work in :func:`asyncio.to_thread` so the event loop never stalls.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.errors import InfraError
from app.infra import csv_io
from app.infra import excel as excel_adapter

__all__ = ["parse_table"]


def _csv_rows(content: bytes) -> list[dict[str, Any]]:
    """Parse CSV bytes and widen the row type for the async callers.

    Args:
        content: Raw CSV bytes.

    Returns:
        list[dict[str, Any]]: Parsed rows (values remain strings).
    """
    rows = csv_io.parse_dicts(content)
    return [dict(row) for row in rows]


def _xlsx_rows(content: bytes) -> list[dict[str, Any]]:
    """Parse XLSX bytes using openpyxl and return row dicts.

    Args:
        content: Raw ``.xlsx`` bytes.

    Returns:
        list[dict[str, Any]]: Parsed rows.
    """
    workbook = excel_adapter.open_workbook(content)
    try:
        return excel_adapter.read_rows(workbook)
    finally:
        workbook.close()


async def parse_table(filename: str, content: bytes) -> list[dict[str, Any]]:
    """Dispatch ``filename``/``content`` to the CSV or XLSX parser.

    Args:
        filename: Original filename; only the extension is inspected
            (case-insensitive).
        content: Raw file bytes.

    Returns:
        list[dict[str, Any]]: Parsed rows. CSV values are ``str``; XLSX values
        are whatever openpyxl emits (``str``/``int``/``float``/``datetime``/
        ``None``).

    Raises:
        InfraError: ``TABULAR_001`` if the extension is not supported.
        InfraError: ``CSV_001`` or ``SYS_002`` propagated from the underlying
            parsers on decode / parse failures.
    """
    if not filename:
        raise InfraError("TABULAR_001", "Empty filename")
    lower = filename.lower()
    if lower.endswith(".csv"):
        return await asyncio.to_thread(_csv_rows, content)
    if lower.endswith(".xlsx"):
        return await asyncio.to_thread(_xlsx_rows, content)
    raise InfraError("TABULAR_001", f"Unsupported file extension: {filename!r}")
