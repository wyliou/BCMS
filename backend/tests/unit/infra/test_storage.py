"""Unit tests for :mod:`app.infra.storage`."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import InfraError
from app.infra import storage


async def test_save_returns_opaque_key(storage_tmp_root: Path) -> None:
    """save() returns a POSIX key rooted under the category."""
    key = await storage.save("uploads", "budget.xlsx", b"abc")
    assert key.startswith("uploads/")
    assert key.endswith("_budget.xlsx")
    assert (storage_tmp_root / key).read_bytes() == b"abc"


async def test_save_and_read_round_trip(storage_tmp_root: Path) -> None:
    """read() returns the bytes that were saved."""
    del storage_tmp_root
    key = await storage.save("templates", "template.xlsx", b"xyz123")
    assert await storage.read(key) == b"xyz123"


async def test_delete_is_idempotent(storage_tmp_root: Path) -> None:
    """Deleting a missing key must not raise."""
    del storage_tmp_root
    key = await storage.save("exports", "export.xlsx", b"hello")
    await storage.delete(key)
    await storage.delete(key)  # idempotent


async def test_unknown_category_raises(storage_tmp_root: Path) -> None:
    """Unknown categories raise ``SYS_002``."""
    del storage_tmp_root
    with pytest.raises(InfraError) as excinfo:
        await storage.save("bogus", "x.bin", b"x")
    assert excinfo.value.code == "SYS_002"


async def test_read_missing_key_raises(storage_tmp_root: Path) -> None:
    """Missing files raise ``SYS_002``."""
    del storage_tmp_root
    with pytest.raises(InfraError):
        await storage.read("uploads/2099/01/missing_file.bin")


async def test_save_two_distinct_keys(storage_tmp_root: Path) -> None:
    """Two saves with the same filename get unique keys."""
    del storage_tmp_root
    key_a = await storage.save("uploads", "dupe.csv", b"a")
    key_b = await storage.save("uploads", "dupe.csv", b"b")
    assert key_a != key_b


async def test_path_traversal_rejected(storage_tmp_root: Path) -> None:
    """Attempting to read ``..`` is blocked."""
    del storage_tmp_root
    with pytest.raises(InfraError):
        await storage.read("../escape")


async def test_filename_sanitized(storage_tmp_root: Path) -> None:
    """Filenames with path separators are sanitized."""
    del storage_tmp_root
    key = await storage.save("uploads", "..\\..\\pwned.xlsx", b"z")
    assert ".." not in key
    assert "\\" not in key
