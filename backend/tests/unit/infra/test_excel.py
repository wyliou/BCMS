"""Unit tests for :mod:`app.infra.excel`."""

from __future__ import annotations

import pytest

from app.core.errors import InfraError
from app.infra import excel as excel_adapter


def _build_xlsx_bytes(rows: list[list[object]]) -> bytes:
    """Build an in-memory workbook with one sheet populated from ``rows``."""
    wb = excel_adapter.write_workbook()
    sheet = wb.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    return excel_adapter.workbook_to_bytes(wb)


def test_open_workbook_roundtrip() -> None:
    """A workbook serialized via ``workbook_to_bytes`` can be reopened."""
    content = _build_xlsx_bytes([["dept", "amount"], ["4023", 100]])
    wb = excel_adapter.open_workbook(content)
    try:
        assert wb.active is not None
    finally:
        wb.close()


def test_open_workbook_invalid_bytes_raises() -> None:
    """Garbage bytes raise :class:`InfraError` with ``SYS_002``."""
    with pytest.raises(InfraError) as excinfo:
        excel_adapter.open_workbook(b"not a zip")
    assert excinfo.value.code == "SYS_002"


def test_read_rows_returns_dicts() -> None:
    """Header row becomes keys; subsequent rows become dicts."""
    content = _build_xlsx_bytes(
        [
            ["dept", "amount"],
            ["4023", 100],
            ["4024", 200],
        ]
    )
    wb = excel_adapter.open_workbook(content)
    try:
        rows = excel_adapter.read_rows(wb)
    finally:
        wb.close()
    assert rows == [
        {"dept": "4023", "amount": 100},
        {"dept": "4024", "amount": 200},
    ]


def test_read_rows_skips_empty_rows() -> None:
    """All-empty rows are filtered out."""
    content = _build_xlsx_bytes(
        [
            ["dept", "amount"],
            ["4023", 100],
            [None, None],
            ["4024", 200],
        ]
    )
    wb = excel_adapter.open_workbook(content)
    try:
        rows = excel_adapter.read_rows(wb)
    finally:
        wb.close()
    assert len(rows) == 2


def test_read_rows_unknown_sheet_raises() -> None:
    """Named sheet that doesn't exist raises ``SYS_002``."""
    content = _build_xlsx_bytes([["a"], [1]])
    wb = excel_adapter.open_workbook(content)
    try:
        with pytest.raises(InfraError):
            excel_adapter.read_rows(wb, sheet_name="NoSuchSheet")
    finally:
        wb.close()


def test_workbook_to_bytes_produces_non_empty_output() -> None:
    """Serialization produces a non-empty byte string."""
    wb = excel_adapter.write_workbook()
    payload = excel_adapter.workbook_to_bytes(wb)
    assert isinstance(payload, bytes)
    assert len(payload) > 0
