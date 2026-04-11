# Spec: infra/storage

Module: `backend/src/app/infra/storage/__init__.py`
Tests: `backend/tests/unit/infra/test_storage.py`

## FRs

- FR-009, FR-010 (template files)
- FR-011, FR-012 (budget upload files)
- FR-017 (async export files)
- FR-024–029 (personnel and shared cost files)

## Exports

```python
async def save(category: str, filename: str, content: bytes) -> str:
    """Save content to the appropriate directory for the given category.

    Wraps blocking file I/O in run_in_threadpool so the async event loop is not blocked.
    The storage key is an opaque relative path (e.g. "uploads/abc123/file.xlsx") that
    callers store in the DB as file_path_enc (after encryption by infra/crypto).

    Args:
        category (str): One of 'uploads', 'templates', 'exports'. Determines root dir.
        filename (str): Original filename, used to derive the stored filename.
            A UUID-based subdirectory is prepended to avoid collisions.
        content (bytes): File bytes to write.

    Returns:
        str: Opaque storage key (relative POSIX path from the storage root).

    Raises:
        InfraError: code='SYS_002' if the directory is missing or write fails.
    """

async def read(storage_key: str) -> bytes:
    """Read and return file content for the given storage key.

    Wraps blocking file I/O in run_in_threadpool.

    Args:
        storage_key (str): Opaque key returned by save().

    Returns:
        bytes: File content.

    Raises:
        InfraError: code='SYS_002' if the file is not found or read fails.
    """

async def delete(storage_key: str) -> None:
    """Delete the file at the given storage key.

    Idempotent: silently succeeds if the file does not exist.
    Wraps blocking file I/O in run_in_threadpool.

    Args:
        storage_key (str): Opaque key returned by save().

    Raises:
        InfraError: code='SYS_002' on unexpected OS error.
    """
```

## Imports

| Module | Symbols |
|---|---|
| `pathlib` | `Path` |
| `uuid` | `uuid4` |
| `asyncio` | (used internally; actual threadpool via starlette) |
| `starlette.concurrency` | `run_in_threadpool` |
| `structlog` | `get_logger` |
| `app.config` | `get_settings` |
| `app.core.errors` | `InfraError` |

## Category → Directory Mapping

| Category | Settings field | Directory |
|---|---|---|
| `"uploads"` | `settings.upload_dir` | `BC_UPLOAD_DIR` |
| `"templates"` | `settings.template_dir` | `BC_TEMPLATE_DIR` |
| `"exports"` | `settings.export_dir` | `BC_EXPORT_DIR` |

## Storage Key Format

`{category}/{uuid4_hex}/{sanitized_filename}`

Example: `uploads/3f7a1b2c4d5e6f7a8b9c0d1e2f3a4b5c/budget_2026.xlsx`

The category prefix enables future migration (move category to separate mount). The UUID subdirectory prevents filename collisions.

## Side Effects

- Creates UUID-named subdirectory on `save` if it does not exist (`mkdir(parents=True, exist_ok=True)`).
- `delete` calls `Path.unlink(missing_ok=True)` — no error if already absent.
- All path operations use `pathlib.Path` with forward-slash separator (POSIX style).

## Gotchas

- **Never use `open()` directly in domain code.** This module wraps all file I/O. Domain modules receive and store only the opaque `storage_key`.
- The `storage_key` stored in the DB is NOT the actual filesystem path; the filesystem path is derived at read time by resolving `category_dir / key`. This means the category root can be remounted without changing stored keys.
- `run_in_threadpool` from Starlette is the correct mechanism — do NOT use `asyncio.to_thread` as it bypasses Starlette's threadpool limit.
- Filename sanitization: strip path separators and null bytes from `filename` before constructing the path.
- The actual file_path stored in the DB is the `file_path_enc` (AES-encrypted storage key). Domain services encrypt before storing, decrypt before calling `read()`. This module does NOT know about encryption — it operates on plain string keys.

## Consistency Constraints

- **CR-001 Stage B check:** *"This module raises only error codes already present in `app.core.errors.ERROR_REGISTRY`. New codes must be added to the registry in the same PR."*
  - All failures raise `InfraError("SYS_002", ...)`.

## Tests

1. `test_save_creates_file_and_returns_key` — save bytes to `"uploads"` category; assert returned key is non-empty string, file exists on disk (`tmp_path`-rooted).
2. `test_read_returns_saved_bytes` — save then read; assert bytes are identical.
3. `test_delete_removes_file` — save then delete; assert `read` afterwards raises `InfraError`.
4. `test_delete_idempotent` — delete a non-existent key; assert no exception.
5. `test_save_unknown_category_raises` — `save("bad_cat", ...)` raises `InfraError("SYS_002", ...)`.
6. `test_read_missing_key_raises` — `read("uploads/nonexistent/file.xlsx")` raises `InfraError("SYS_002", ...)`.
7. `test_different_saves_unique_keys` — two saves of same filename produce different keys.
