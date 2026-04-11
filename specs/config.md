# Spec: config

Module: `backend/src/app/config.py` | Tests: `backend/tests/unit/test_config.py` | FRs: (none — shared settings)

## Exports

```python
class Settings(BaseSettings):
    """Pydantic Settings class loading all BC_* environment variables.

    All fields validated at startup. Missing required fields crash fast with a clear error.
    """

def get_settings() -> Settings:
    """Return the singleton Settings instance (cached via lru_cache).

    Returns:
        Settings: Application settings loaded from environment / .env file.
    """
```

## Imports

- `pydantic_settings`: `BaseSettings`
- `pydantic`: `Field`, `model_validator`
- `functools`: `lru_cache`

## All BC_* fields (from architecture §7)

### Database
| Field | Type | Required | Default | Env var |
|---|---|---|---|---|
| `database_url` | `str` | Yes | — | `BC_DATABASE_URL` |
| `database_pool_size` | `int` | No | `10` | `BC_DATABASE_POOL_SIZE` |
| `database_max_overflow` | `int` | No | `5` | `BC_DATABASE_MAX_OVERFLOW` |

### Cryptography
| Field | Type | Required | Default | Env var |
|---|---|---|---|---|
| `crypto_key` | `str` | Yes | — | `BC_CRYPTO_KEY` |
| `crypto_key_id` | `str` | Yes | — | `BC_CRYPTO_KEY_ID` |
| `audit_hmac_key` | `str` | Yes | — | `BC_AUDIT_HMAC_KEY` |
| `user_lookup_hmac_key` | `str` | Yes | — | `BC_USER_LOOKUP_HMAC_KEY` |

### SSO
| Field | Type | Required | Default | Env var |
|---|---|---|---|---|
| `sso_protocol` | `str` | Yes | — | `BC_SSO_PROTOCOL` (must be `"oidc"` or `"saml2"`) |
| `sso_client_id` | `str` | Yes | — | `BC_SSO_CLIENT_ID` |
| `sso_client_secret` | `str \| None` | No | `None` | `BC_SSO_CLIENT_SECRET` |
| `sso_discovery_url` | `str \| None` | No | `None` | `BC_SSO_DISCOVERY_URL` |
| `sso_metadata_url` | `str \| None` | No | `None` | `BC_SSO_METADATA_URL` |
| `sso_redirect_uri` | `str` | Yes | — | `BC_SSO_REDIRECT_URI` |
| `sso_scopes` | `str` | No | `"openid profile email groups"` | `BC_SSO_SCOPES` |
| `sso_role_claim` | `str` | No | `"groups"` | `BC_SSO_ROLE_CLAIM` |
| `sso_role_mapping` | `dict[str, str]` | Yes | — | `BC_SSO_ROLE_MAPPING` (JSON string) |

### Sessions
| Field | Type | Required | Default | Env var |
|---|---|---|---|---|
| `jwt_signing_key` | `str` | Yes | — | `BC_JWT_SIGNING_KEY` |
| `session_idle_minutes` | `int` | No | `30` | `BC_SESSION_IDLE_MINUTES` |
| `session_absolute_hours` | `int` | No | `8` | `BC_SESSION_ABSOLUTE_HOURS` |
| `cookie_domain` | `str` | Yes | — | `BC_COOKIE_DOMAIN` |
| `cookie_secure` | `bool` | No | `True` | `BC_COOKIE_SECURE` |

### SMTP
| Field | Type | Required | Default | Env var |
|---|---|---|---|---|
| `smtp_host` | `str` | Yes | — | `BC_SMTP_HOST` |
| `smtp_port` | `int` | No | `587` | `BC_SMTP_PORT` |
| `smtp_use_tls` | `bool` | No | `True` | `BC_SMTP_USE_TLS` |
| `smtp_user` | `str \| None` | No | `None` | `BC_SMTP_USER` |
| `smtp_password` | `str \| None` | No | `None` | `BC_SMTP_PASSWORD` |
| `smtp_from` | `str` | Yes | — | `BC_SMTP_FROM` |
| `smtp_reply_to` | `str \| None` | No | `None` | `BC_SMTP_REPLY_TO` |

### Storage
| Field | Type | Required | Default | Env var |
|---|---|---|---|---|
| `upload_dir` | `str` | Yes | — | `BC_UPLOAD_DIR` |
| `template_dir` | `str` | Yes | — | `BC_TEMPLATE_DIR` |
| `export_dir` | `str` | Yes | — | `BC_EXPORT_DIR` |
| `max_upload_bytes` | `int` | No | `10485760` | `BC_MAX_UPLOAD_BYTES` |
| `max_upload_rows` | `int` | No | `5000` | `BC_MAX_UPLOAD_ROWS` |

### Application
| Field | Type | Required | Default | Env var |
|---|---|---|---|---|
| `log_level` | `str` | No | `"INFO"` | `BC_LOG_LEVEL` |
| `frontend_origin` | `str` | Yes | — | `BC_FRONTEND_ORIGIN` |
| `timezone` | `str` | No | `"Asia/Taipei"` | `BC_TIMEZONE` |
| `reopen_window_days` | `int` | No | `7` | `BC_REOPEN_WINDOW_DAYS` |
| `deadline_reminder_cron` | `str` | No | `"0 9 * * *"` | `BC_DEADLINE_REMINDER_CRON` |
| `async_export_threshold` | `int` | No | `1000` | `BC_ASYNC_EXPORT_THRESHOLD` |
| `api_base_url` | `str` | Yes | — | `BC_API_BASE_URL` |
| `request_id_header` | `str` | No | `"X-Request-ID"` | `BC_REQUEST_ID_HEADER` |
| `ip_allowlist` | `str \| None` | No | `None` | `BC_IP_ALLOWLIST` |

### Job Runner
| Field | Type | Required | Default | Env var |
|---|---|---|---|---|
| `jobs_worker_id` | `str \| None` | No | `None` | `BC_JOBS_WORKER_ID` |
| `jobs_poll_interval_seconds` | `int` | No | `5` | `BC_JOBS_POLL_INTERVAL_SECONDS` |
| `jobs_max_attempts` | `int` | No | `3` | `BC_JOBS_MAX_ATTEMPTS` |

## Side Effects

- `get_settings()` is decorated with `@lru_cache()`. Call it once at startup; subsequent calls return the cached singleton.
- `BaseSettings` reads `.env` file in the project root when present (configured via `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")`).

## Gotchas

- `BC_SSO_ROLE_MAPPING` is a JSON string in the environment; Pydantic must parse it as `dict[str, str]`. Use a `@field_validator` or Pydantic v2's `json` mode for that field.
- `sso_protocol` must be validated to `"oidc"` or `"saml2"`; raise `ValueError` otherwise.
- `crypto_key` is hex-encoded 32-byte key; a `@model_validator` should check `len(bytes.fromhex(crypto_key)) == 32`.
- Tests must use `monkeypatch.setenv(...)` + clear `get_settings.cache_clear()` after each test.

## Tests

1. `test_settings_loads_with_required_env_vars` — provide all required vars via monkeypatch; `get_settings()` succeeds.
2. `test_missing_required_field_raises` — omit `BC_DATABASE_URL`; assert `ValidationError` at construction.
3. `test_sso_role_mapping_parsed_as_dict` — set `BC_SSO_ROLE_MAPPING='{"BC_FINANCE":"FinanceAdmin"}'`; assert `settings.sso_role_mapping == {"BC_FINANCE": "FinanceAdmin"}`.
4. `test_defaults_applied` — set only required vars; assert `settings.max_upload_bytes == 10485760`.
5. `test_get_settings_is_cached` — call `get_settings()` twice; assert `id(a) == id(b)`.

## Constraints

None.
