"""Unit tests for :mod:`app.infra.csv_io`."""

from __future__ import annotations

import pytest

from app.core.errors import InfraError
from app.infra import csv_io


def test_parse_valid_csv() -> None:
    """Normal two-column CSV parses to dicts."""
    content = b"dept_id,amount\n4023,100\n4024,200\n"
    rows = csv_io.parse_dicts(content)
    assert rows == [
        {"dept_id": "4023", "amount": "100"},
        {"dept_id": "4024", "amount": "200"},
    ]


def test_parse_header_only_returns_empty_list() -> None:
    """Header-only CSV returns an empty list."""
    assert csv_io.parse_dicts(b"a,b\n") == []


def test_parse_skips_blank_rows() -> None:
    """Blank rows are skipped."""
    content = b"a,b\n1,2\n,\n3,4\n"
    rows = csv_io.parse_dicts(content)
    assert rows == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]


def test_parse_rejects_non_utf8() -> None:
    """Big5-encoded input raises ``CSV_001``."""
    big5 = "部門,金額\n業務,100\n".encode("big5")
    with pytest.raises(InfraError) as excinfo:
        csv_io.parse_dicts(big5)
    assert excinfo.value.code == "CSV_001"


def test_parse_handles_utf8_bom() -> None:
    """UTF-8 BOM is stripped before decoding."""
    content = b"\xef\xbb\xbfdept_id,amount\n1,2\n"
    rows = csv_io.parse_dicts(content)
    assert rows == [{"dept_id": "1", "amount": "2"}]


def test_parse_non_bytes_raises() -> None:
    """Passing a str raises ``CSV_001``."""
    with pytest.raises(InfraError):
        csv_io.parse_dicts("a,b\n1,2\n")  # type: ignore[arg-type]
