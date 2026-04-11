"""Unit tests for :mod:`app.config`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


def test_settings_loads_with_defaults() -> None:
    """Baseline fixture env must produce a valid :class:`Settings`."""
    settings = get_settings()
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.crypto_key_id == "k-test"
    assert settings.timezone == "Asia/Taipei"


def test_settings_max_upload_bytes_default() -> None:
    """Default max upload size is 10 MiB."""
    settings = get_settings()
    assert settings.max_upload_bytes == 10 * 1024 * 1024
    assert settings.max_upload_rows == 5000


def test_missing_crypto_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dropping a required field must fail fast."""
    monkeypatch.delenv("BC_CRYPTO_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_invalid_crypto_key_length_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """The crypto key validator rejects non-32-byte values."""
    monkeypatch.setenv("BC_CRYPTO_KEY", "abcd")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_sso_role_mapping_parsed_from_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """JSON string env var decodes to ``dict[str, str]``."""
    monkeypatch.setenv(
        "BC_SSO_ROLE_MAPPING",
        '{"BC_FINANCE":"FinanceAdmin","BC_HR":"HRAdmin"}',
    )
    get_settings.cache_clear()
    settings = Settings()
    assert settings.sso_role_mapping == {
        "BC_FINANCE": "FinanceAdmin",
        "BC_HR": "HRAdmin",
    }


def test_sso_role_mapping_rejects_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed JSON raises a settings / validation error."""
    from pydantic_settings.exceptions import SettingsError

    monkeypatch.setenv("BC_SSO_ROLE_MAPPING", "not json")
    get_settings.cache_clear()
    with pytest.raises((ValidationError, SettingsError)):
        Settings()  # type: ignore[call-arg]  # type: ignore[call-arg]


def test_get_settings_is_cached() -> None:
    """The singleton must be returned across calls until cache_clear."""
    first = get_settings()
    second = get_settings()
    assert first is second


def test_log_level_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lowercase levels are normalized to uppercase."""
    monkeypatch.setenv("BC_LOG_LEVEL", "debug")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.log_level == "DEBUG"


def test_invalid_log_level_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown level values raise validation error."""
    monkeypatch.setenv("BC_LOG_LEVEL", "VERBOSE")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]
