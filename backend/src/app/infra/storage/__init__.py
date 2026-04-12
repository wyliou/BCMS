"""Async file I/O adapter rooted at :attr:`Settings.storage_root`.

Domain modules NEVER call ``open()`` or construct filesystem paths directly —
they call :func:`save`, :func:`read`, and :func:`delete` and store only the
opaque ``storage_key`` (a POSIX-style relative path) returned by :func:`save`.
Blocking disk operations are offloaded to the asyncio thread pool so the
event loop never stalls.

Storage key format::

    {category}/{yyyy}/{mm}/{uuid_hex}_{safe_filename}

The date sub-directory is derived from the current UTC time so that storage
scales without a flat directory explosion. ``safe_filename`` is the original
filename with path separators and null bytes stripped.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from uuid import uuid4

from app.config import get_settings
from app.core.clock import now_utc
from app.core.errors import InfraError

__all__ = ["save", "read", "delete", "resolve_path"]


_ALLOWED_CATEGORIES = {
    "uploads",
    "templates",
    "exports",
    "budget_uploads",
    "personnel",
    "shared_costs",
}
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize_filename(filename: str) -> str:
    """Return a filesystem-safe filename.

    Strips path separators, null bytes, and any characters outside the
    conservative ``[A-Za-z0-9._-]`` set. Collapses whitespace to underscores.

    Args:
        filename: User-supplied filename.

    Returns:
        str: Sanitized filename (never empty — defaults to ``"file"``).
    """
    if not filename:
        return "file"
    # Reason: POSIX and Windows both treat these as separators; strip before
    # further cleaning so we never surface path components from user input.
    base = filename.replace("\\", "/").split("/")[-1].replace("\x00", "")
    base = base.strip().replace(" ", "_")
    cleaned = _SAFE_FILENAME_RE.sub("_", base)
    return cleaned or "file"


def _validate_category(category: str) -> None:
    """Validate that ``category`` is one of the allowed roots.

    Args:
        category: Category name to validate.

    Raises:
        InfraError: ``SYS_002`` if the category is unknown.
    """
    if category not in _ALLOWED_CATEGORIES:
        raise InfraError("SYS_002", f"Unknown storage category: {category!r}")


def _storage_root() -> Path:
    """Return the absolute :class:`Path` of the storage root.

    Returns:
        Path: The configured :attr:`Settings.storage_root` as a ``Path``.
    """
    return Path(get_settings().storage_root).resolve()


def _validate_key(storage_key: str) -> None:
    """Reject storage keys that attempt path traversal.

    Args:
        storage_key: Storage key to validate.

    Raises:
        InfraError: ``SYS_002`` if the key is absolute or contains ``..``.
    """
    if not storage_key or storage_key.startswith(("/", "\\")):
        raise InfraError("SYS_002", f"Invalid storage key: {storage_key!r}")
    normalized = storage_key.replace("\\", "/")
    parts = normalized.split("/")
    if ".." in parts or any(p == "" for p in parts):
        raise InfraError("SYS_002", f"Invalid storage key: {storage_key!r}")


def resolve_path(storage_key: str) -> Path:
    """Resolve an opaque storage key to an absolute filesystem path.

    Args:
        storage_key: Opaque key previously returned by :func:`save`.

    Returns:
        Path: Absolute path under :attr:`Settings.storage_root`.

    Raises:
        InfraError: ``SYS_002`` if the key escapes the storage root.
    """
    _validate_key(storage_key)
    root = _storage_root()
    candidate = (root / storage_key).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise InfraError("SYS_002", "Storage key escapes storage root") from exc
    return candidate


def _build_key(category: str, filename: str) -> str:
    """Build a fresh opaque storage key for ``category`` + ``filename``.

    Args:
        category: Validated category name.
        filename: Sanitized filename.

    Returns:
        str: POSIX-style relative path (with forward slashes).
    """
    safe_name = _sanitize_filename(filename)
    now = now_utc()
    uid = uuid4().hex
    return f"{category}/{now.year:04d}/{now.month:02d}/{uid}_{safe_name}"


def _write_bytes(path: Path, content: bytes) -> None:
    """Create parent directories and write ``content`` to ``path``.

    Args:
        path: Destination path.
        content: Raw bytes to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(content)


def _read_bytes(path: Path) -> bytes:
    """Read an entire file into memory.

    Args:
        path: Path to read.

    Returns:
        bytes: File contents.
    """
    with path.open("rb") as fh:
        return fh.read()


async def save(category: str, filename: str, content: bytes) -> str:
    """Save ``content`` under ``category`` and return the opaque storage key.

    Args:
        category: One of ``"uploads"``, ``"templates"``, ``"exports"``.
        filename: Original filename (used to derive a sanitized leaf name).
        content: Raw bytes to persist.

    Returns:
        str: Opaque storage key to pass back to :func:`read` / :func:`delete`.

    Raises:
        InfraError: ``SYS_002`` if the category is unknown or the write fails.
    """
    _validate_category(category)
    if not isinstance(content, (bytes, bytearray)):
        raise InfraError("SYS_002", "storage.save requires bytes content")
    key = _build_key(category, filename)
    path = resolve_path(key)
    try:
        await asyncio.to_thread(_write_bytes, path, bytes(content))
    except OSError as exc:
        raise InfraError("SYS_002", f"storage.save failed: {exc}") from exc
    return key


async def read(storage_key: str) -> bytes:
    """Read the file identified by ``storage_key``.

    Args:
        storage_key: Opaque key returned by :func:`save`.

    Returns:
        bytes: File contents.

    Raises:
        InfraError: ``SYS_002`` if the file does not exist or cannot be read.
    """
    path = resolve_path(storage_key)
    try:
        return await asyncio.to_thread(_read_bytes, path)
    except FileNotFoundError as exc:
        raise InfraError("SYS_002", f"storage.read not found: {storage_key}") from exc
    except OSError as exc:
        raise InfraError("SYS_002", f"storage.read failed: {exc}") from exc


async def delete(storage_key: str) -> None:
    """Delete the file identified by ``storage_key``.

    Idempotent — deleting a missing key is a no-op.

    Args:
        storage_key: Opaque key returned by :func:`save`.

    Raises:
        InfraError: ``SYS_002`` on unexpected OS errors (other than "missing").
    """
    path = resolve_path(storage_key)
    try:
        await asyncio.to_thread(path.unlink, True)
    except OSError as exc:
        raise InfraError("SYS_002", f"storage.delete failed: {exc}") from exc
