"""Pydantic Settings — every ``BC_*`` environment variable for the application.

The single :class:`Settings` class is the only place the backend reads process
environment. All downstream modules call :func:`get_settings` (lru-cached), never
``os.environ`` directly. Fields are typed; missing required fields crash fast
at ``Settings()`` construction time.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "get_settings"]


class Settings(BaseSettings):
    """Application settings loaded from environment / ``.env`` file.

    Every field name maps 1:1 to an environment variable using the ``BC_``
    prefix (case-insensitive) per architecture §7. Required fields have no
    default; omitting them causes ``Settings()`` to raise ``ValidationError``
    at construction time which is the desired fail-fast behavior.
    """

    model_config = SettingsConfigDict(
        env_prefix="BC_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database --------------------------------------------------------
    database_url: str = Field(..., description="Async SQLAlchemy URL (asyncpg).")
    database_pool_size: int = Field(default=10)
    database_max_overflow: int = Field(default=5)

    # --- Cryptography ----------------------------------------------------
    crypto_key: str = Field(..., description="Hex-encoded 32-byte AES-256 master key.")
    crypto_key_id: str = Field(default="k-default", description="Active key identifier.")
    audit_hmac_key: str = Field(..., description="Hex-encoded HMAC key for audit chain.")
    user_lookup_hmac_key: str = Field(
        default="",
        description="Hex-encoded HMAC key for email/sso_id lookup hashes.",
    )

    # --- Session / JWT ---------------------------------------------------
    session_secret: str = Field(default="", description="Opaque session signing secret.")
    jwt_signing_key: str = Field(default="", description="HS256 JWT signing key.")
    session_idle_minutes: int = Field(default=30)
    session_absolute_hours: int = Field(default=8)
    session_ttl_seconds: int = Field(default=1800)
    refresh_ttl_seconds: int = Field(default=28800)
    cookie_domain: str = Field(default="")
    cookie_secure: bool = Field(default=True)

    # --- SMTP ------------------------------------------------------------
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_use_tls: bool = Field(default=True)
    smtp_user: str | None = Field(default=None)
    smtp_password: str | None = Field(default=None)
    email_from: str = Field(default="budget-noreply@example.invalid")
    smtp_reply_to: str | None = Field(default=None)

    # --- SSO -------------------------------------------------------------
    sso_provider: str = Field(default="oidc")
    sso_client_id: str = Field(default="")
    sso_client_secret: str | None = Field(default=None)
    sso_issuer: str = Field(default="")
    sso_discovery_url: str | None = Field(default=None)
    sso_metadata_url: str | None = Field(default=None)
    sso_redirect_uri: str = Field(default="")
    sso_scopes: str = Field(default="openid profile email groups")
    sso_role_claim: str = Field(default="groups")
    sso_role_mapping: dict[str, str] = Field(default_factory=dict)

    # --- Storage ---------------------------------------------------------
    storage_root: str = Field(default="./var/storage")
    upload_dir: str = Field(default="./var/storage/uploads")
    template_dir: str = Field(default="./var/storage/templates")
    export_dir: str = Field(default="./var/storage/exports")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024)
    max_upload_rows: int = Field(default=5000)

    # --- Application -----------------------------------------------------
    log_level: str = Field(default="INFO")
    frontend_origin: str = Field(default="http://localhost:5173")
    timezone: str = Field(default="Asia/Taipei")
    reopen_window_days: int = Field(default=30)
    deadline_reminder_cron: str = Field(default="0 9 * * *")
    async_export_threshold: int = Field(default=1000)
    api_base_url: str = Field(default="http://localhost:8000")
    request_id_header: str = Field(default="X-Request-ID")
    ip_allowlist: str | None = Field(default=None)

    # --- Jobs ------------------------------------------------------------
    jobs_worker_id: str | None = Field(default=None)
    jobs_poll_interval_seconds: int = Field(default=5)
    jobs_max_attempts: int = Field(default=3)

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("sso_role_mapping", mode="before")
    @classmethod
    def _parse_role_mapping(cls, value: Any, info: ValidationInfo) -> Any:
        """Parse ``BC_SSO_ROLE_MAPPING`` JSON string into a ``dict[str, str]``.

        Args:
            value: Raw environment value — either a JSON string like
                ``'{"BC_FINANCE":"FinanceAdmin"}'`` or an already-parsed dict.
            info: Pydantic validation context (unused).

        Returns:
            dict[str, str]: Parsed mapping. Empty dict if value is empty/None.

        Raises:
            ValueError: If ``value`` is a string that cannot be decoded as JSON
                object whose values are all strings.
        """
        del info
        if value is None or value == "":
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError(f"BC_SSO_ROLE_MAPPING must be JSON object; got {value!r}") from exc
            if not isinstance(parsed, dict):
                raise ValueError("BC_SSO_ROLE_MAPPING must decode to a JSON object")
            return parsed
        raise ValueError(f"BC_SSO_ROLE_MAPPING has unsupported type: {type(value).__name__}")

    @field_validator("crypto_key")
    @classmethod
    def _validate_crypto_key(cls, value: str) -> str:
        """Ensure ``BC_CRYPTO_KEY`` is a hex-encoded 32-byte value.

        Args:
            value: Hex string (64 characters for 32 bytes).

        Returns:
            str: The validated hex string.

        Raises:
            ValueError: If the value is not valid hex or not exactly 32 bytes.
        """
        try:
            raw = bytes.fromhex(value)
        except ValueError as exc:
            raise ValueError("BC_CRYPTO_KEY must be hex-encoded") from exc
        if len(raw) != 32:
            raise ValueError(f"BC_CRYPTO_KEY must decode to 32 bytes; got {len(raw)}")
        return value

    @field_validator("audit_hmac_key")
    @classmethod
    def _validate_audit_hmac_key(cls, value: str) -> str:
        """Ensure ``BC_AUDIT_HMAC_KEY`` decodes to at least 32 bytes.

        Args:
            value: Hex string.

        Returns:
            str: The validated hex string.

        Raises:
            ValueError: If the value is not valid hex or shorter than 32 bytes.
        """
        try:
            raw = bytes.fromhex(value)
        except ValueError as exc:
            raise ValueError("BC_AUDIT_HMAC_KEY must be hex-encoded") from exc
        if len(raw) < 32:
            raise ValueError("BC_AUDIT_HMAC_KEY must decode to at least 32 bytes")
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        """Normalize and validate ``BC_LOG_LEVEL``.

        Args:
            value: Level name (case-insensitive). One of DEBUG/INFO/WARN/WARNING/ERROR.

        Returns:
            str: Upper-cased canonical level name.

        Raises:
            ValueError: If ``value`` is not a recognized level.
        """
        normalized = value.upper()
        if normalized == "WARN":
            normalized = "WARNING"
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"BC_LOG_LEVEL invalid: {value!r}")
        return normalized


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton.

    Result is memoized via ``lru_cache``. Tests that mutate environment
    variables MUST call ``get_settings.cache_clear()`` between cases.

    Returns:
        Settings: Loaded application settings.
    """
    return Settings()  # type: ignore[call-arg]
