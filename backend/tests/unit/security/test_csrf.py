"""Unit tests for :mod:`app.core.security.csrf`."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.errors import ForbiddenError
from app.core.security.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    issue_csrf_token,
    verify_csrf,
    verify_csrf_token,
)


def test_issue_csrf_token_length() -> None:
    """Issued tokens are 64 hex characters (32 bytes)."""
    token = issue_csrf_token()
    assert len(token) == 64
    int(token, 16)  # Will raise if not valid hex.


def test_verify_csrf_token_matching() -> None:
    """Matching tokens pass silently."""
    token = issue_csrf_token()
    verify_csrf_token(token, token)


def test_verify_csrf_token_mismatch_raises_rbac_001() -> None:
    """Different tokens raise ForbiddenError(RBAC_001)."""
    with pytest.raises(ForbiddenError) as excinfo:
        verify_csrf_token(issue_csrf_token(), issue_csrf_token())
    assert excinfo.value.code == "RBAC_001"


def test_verify_csrf_token_missing_raises_rbac_001() -> None:
    """Missing cookie or header raises ForbiddenError(RBAC_001)."""
    with pytest.raises(ForbiddenError):
        verify_csrf_token(None, "abc")
    with pytest.raises(ForbiddenError):
        verify_csrf_token("abc", None)


def test_verify_csrf_skips_get_requests() -> None:
    """Verification is a no-op for GET/HEAD/OPTIONS."""
    request = MagicMock()
    request.method = "GET"
    request.cookies = {}
    request.headers = {}
    verify_csrf(request)


def test_verify_csrf_enforces_post() -> None:
    """POST requests must carry matching cookie + header."""
    token = issue_csrf_token()
    request = MagicMock()
    request.method = "POST"
    request.cookies = {CSRF_COOKIE_NAME: token}
    request.headers = {CSRF_HEADER_NAME: token}
    verify_csrf(request)

    request.headers = {CSRF_HEADER_NAME: issue_csrf_token()}
    with pytest.raises(ForbiddenError):
        verify_csrf(request)
