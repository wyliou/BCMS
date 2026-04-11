"""Root pytest configuration + shared fixtures.

The Batch 0 tests rely on three things being in place before any test module
is collected:

1. Required ``BC_*`` environment variables have sensible defaults so that
   :class:`app.config.Settings` can be constructed at application-import
   time (``from app.main import app`` triggers ``create_app()``).
2. :func:`app.config.get_settings` is lru-cached — the autouse
   ``_reset_settings_cache`` fixture clears the cache between test functions
   so that monkeypatched env vars take effect.
3. A shared ``storage_root`` directory rooted under ``tmp_path`` is provided
   via the ``storage_tmp_root`` fixture for the infra-storage tests.

Env-var seeding runs at **import time** (not inside a fixture) because
``tests/api/test_main.py`` imports :mod:`app.main` at collection time, which
instantiates :class:`Settings` immediately. A fixture would run too late.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Reason: the Settings class fails fast when required vars are missing. Seed
# defaults at import time so that ``from app.main import app`` succeeds even
# when the developer's shell has no BC_* exports.
_DEFAULT_ENV: dict[str, str] = {
    "BC_DATABASE_URL": "postgresql+asyncpg://bcms:bcms@localhost:5432/bcms_test",
    "BC_CRYPTO_KEY": "0" * 64,
    "BC_CRYPTO_KEY_ID": "k-test",
    "BC_AUDIT_HMAC_KEY": "1" * 64,
    "BC_USER_LOOKUP_HMAC_KEY": "2" * 64,
    "BC_STORAGE_ROOT": "./var/storage",
    "BC_TIMEZONE": "Asia/Taipei",
    "BC_LOG_LEVEL": "INFO",
    "BC_FRONTEND_ORIGIN": "http://localhost:5173",
    "BC_API_BASE_URL": "http://localhost:8000",
    "BC_EMAIL_FROM": "budget-noreply@example.invalid",
    "BC_COOKIE_DOMAIN": "localhost",
    "BC_SSO_PROVIDER": "oidc",
    "BC_SSO_ROLE_MAPPING": '{"BC_FINANCE":"FinanceAdmin"}',
}

for _k, _v in _DEFAULT_ENV.items():
    os.environ.setdefault(_k, _v)


@pytest.fixture(autouse=True)
def _seed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refresh the default env vars for every test via ``monkeypatch``.

    Tests that need different values can monkeypatch them inside the test
    body; this fixture runs first and only sets the variable when it has
    been cleared by a previous test.
    """
    for key, value in _DEFAULT_ENV.items():
        if key not in os.environ:
            monkeypatch.setenv(key, value)


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    """Clear :func:`get_settings` lru_cache between tests."""
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def storage_tmp_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect :data:`Settings.storage_root` to an isolated ``tmp_path``.

    Yields:
        Path: The tmp-root path so tests can inspect the filesystem.
    """
    monkeypatch.setenv("BC_STORAGE_ROOT", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()
