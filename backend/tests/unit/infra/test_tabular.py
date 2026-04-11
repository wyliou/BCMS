"""Unit tests for :mod:`app.infra.tabular`."""

from __future__ import annotations

import pytest

from app.core.errors import InfraError
from app.infra import excel as excel_adapter
from app.infra import tabular


def _build_xlsx_bytes() -> bytes:
    wb = excel_adapter.write_workbook()
    sheet = wb.active
    assert sheet is not None
    sheet.append(["dept_id", "amount"])
    sheet.append(["4023", 100])
    return excel_adapter.workbook_to_bytes(wb)


async def test_csv_dispatch() -> None:
    """``.csv`` filename dispatches to the CSV parser."""
    rows = await tabular.parse_table("data.csv", b"dept_id,amount\n4023,100\n")
    assert rows == [{"dept_id": "4023", "amount": "100"}]


async def test_xlsx_dispatch() -> None:
    """``.xlsx`` filename dispatches to the openpyxl parser."""
    rows = await tabular.parse_table("data.xlsx", _build_xlsx_bytes())
    assert len(rows) == 1
    assert rows[0]["dept_id"] == "4023"


async def test_case_insensitive_extension() -> None:
    """Upper-case extensions work."""
    rows = await tabular.parse_table("DATA.CSV", b"a,b\n1,2\n")
    assert rows == [{"a": "1", "b": "2"}]


async def test_unsupported_extension_raises() -> None:
    """Unknown extensions raise ``TABULAR_001``."""
    with pytest.raises(InfraError) as excinfo:
        await tabular.parse_table("data.xls", b"")
    assert excinfo.value.code == "TABULAR_001"


async def test_empty_filename_raises() -> None:
    """Empty filename raises ``TABULAR_001``."""
    with pytest.raises(InfraError):
        await tabular.parse_table("", b"")
