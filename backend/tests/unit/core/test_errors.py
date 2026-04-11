"""Unit tests for :mod:`app.core.errors`."""

from __future__ import annotations

import re

import pytest

from app.core.errors import (
    ERROR_REGISTRY,
    AppError,
    BatchValidationError,
    ConflictError,
    ForbiddenError,
    InfraError,
    NotFoundError,
    UnauthenticatedError,
)

# ---------------------------------------------------------------------------
# AppError
# ---------------------------------------------------------------------------


def test_app_error_stores_code_and_message() -> None:
    """Basic attribute storage."""
    err = AppError("SYS_003", "boom")
    assert err.code == "SYS_003"
    assert err.message == "boom"
    assert err.http_status == 500


def test_app_error_defaults_message_from_registry() -> None:
    """Omitting ``message`` uses the registry default."""
    err = AppError("CYCLE_001")
    assert err.message == ERROR_REGISTRY["CYCLE_001"][1]


def test_app_error_details_default_none() -> None:
    """``details`` defaults to ``None``."""
    err = AppError("SYS_003")
    assert err.details is None


def test_app_error_is_exception() -> None:
    """Subclass hierarchy check."""
    assert isinstance(AppError("SYS_003"), Exception)


def test_app_error_unknown_code_raises() -> None:
    """Constructing with an unregistered code must raise KeyError."""
    with pytest.raises(KeyError):
        AppError("BOGUS_999")


def test_app_error_to_envelope_shape() -> None:
    """Envelope must match architecture §3 shape."""
    err = AppError("UPLOAD_001", "too big", details=[{"row": 1}])
    envelope = err.to_envelope()
    assert envelope == {
        "error": {
            "code": "UPLOAD_001",
            "message": "too big",
            "details": [{"row": 1}],
        }
    }


# ---------------------------------------------------------------------------
# Subclasses
# ---------------------------------------------------------------------------


def test_batch_validation_error_http_400() -> None:
    """``UPLOAD_007`` maps to HTTP 400."""
    err = BatchValidationError("UPLOAD_007", errors=[])
    assert err.http_status == 400
    assert err.details == []


def test_batch_validation_error_accepts_dict_list() -> None:
    """Plain list-of-dicts is accepted verbatim."""
    payload = [{"row": 1, "code": "UPLOAD_003", "reason": "x"}]
    err = BatchValidationError("UPLOAD_007", errors=payload)
    assert err.details == payload


def test_batch_validation_error_accepts_to_dict_objects() -> None:
    """Objects with ``to_dict()`` are auto-normalized."""

    class FakeRow:
        def __init__(self, row: int) -> None:
            self.row = row

        def to_dict(self) -> dict[str, int]:
            return {"row": self.row}

    err = BatchValidationError("PERS_004", errors=[FakeRow(5), FakeRow(9)])
    assert err.details == [{"row": 5}, {"row": 9}]


def test_not_found_error_http_404() -> None:
    """``ACCOUNT_001`` maps to 404."""
    err = NotFoundError("ACCOUNT_001")
    assert err.http_status == 404


def test_conflict_error_http_409() -> None:
    """``CYCLE_001`` maps to 409."""
    err = ConflictError("CYCLE_001")
    assert err.http_status == 409


def test_forbidden_error_http_403() -> None:
    """``RBAC_001`` maps to 403."""
    err = ForbiddenError("RBAC_001")
    assert err.http_status == 403


def test_unauthenticated_error_http_401() -> None:
    """``AUTH_004`` maps to 401."""
    err = UnauthenticatedError("AUTH_004")
    assert err.http_status == 401


def test_infra_error_sys_001_is_500() -> None:
    """``SYS_001`` maps to 500."""
    err = InfraError("SYS_001")
    assert err.http_status == 500


def test_infra_error_auth_001_is_503() -> None:
    """``AUTH_001`` maps to 503 via the registry."""
    err = InfraError("AUTH_001")
    assert err.http_status == 503


# ---------------------------------------------------------------------------
# ERROR_REGISTRY
# ---------------------------------------------------------------------------


def test_registry_values_are_int_str_tuples() -> None:
    """Every registry entry is ``(int, str)``."""
    for code, value in ERROR_REGISTRY.items():
        assert isinstance(value, tuple) and len(value) == 2, code
        status, message = value
        assert isinstance(status, int)
        assert isinstance(message, str)


def test_registry_keys_match_prefix_pattern() -> None:
    """Every key matches ``[A-Z]+_[0-9]{3}``."""
    pattern = re.compile(r"^[A-Z]+_[0-9]{3}$")
    for code in ERROR_REGISTRY:
        assert pattern.match(code), code


def test_registry_contains_batch_0_additions() -> None:
    """Task-prompt additions must be present."""
    assert "CSV_001" in ERROR_REGISTRY
    assert "TABULAR_001" in ERROR_REGISTRY


def test_registry_contains_architecture_codes() -> None:
    """A spot check for every major prefix family."""
    for code in [
        "AUTH_001",
        "RBAC_001",
        "CYCLE_001",
        "ACCOUNT_001",
        "TPL_001",
        "UPLOAD_001",
        "PERS_001",
        "SHARED_001",
        "REPORT_001",
        "NOTIFY_001",
        "AUDIT_001",
        "SYS_001",
    ]:
        assert code in ERROR_REGISTRY
