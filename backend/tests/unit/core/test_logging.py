"""Unit tests for :mod:`app.core.logging`."""

from __future__ import annotations

import logging

import pytest
import structlog

from app.core import logging as app_logging


def test_configure_logging_accepts_info() -> None:
    """Baseline call with the default level must not raise."""
    app_logging.configure_logging("INFO")


def test_configure_logging_accepts_debug() -> None:
    """DEBUG level is permitted."""
    app_logging.configure_logging("DEBUG")
    # Reason: basicConfig was called with force=True so stdlib root level
    # should now be DEBUG.
    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_accepts_warn_alias() -> None:
    """``WARN`` is an alias for ``WARNING``."""
    app_logging.configure_logging("WARN")
    assert logging.getLogger().level == logging.WARNING


def test_configure_logging_rejects_invalid() -> None:
    """Unknown levels must raise :class:`ValueError`."""
    with pytest.raises(ValueError):
        app_logging.configure_logging("VERBOSE")


def test_bind_request_context_roundtrip() -> None:
    """bind/clear must leave no residue in the contextvars bag."""
    app_logging.configure_logging("INFO")
    app_logging.bind_request_context("req-1", user_id="user-1")
    ctx = structlog.contextvars.get_contextvars()
    assert ctx.get("request_id") == "req-1"
    assert ctx.get("user_id") == "user-1"
    app_logging.clear_request_context()
    assert structlog.contextvars.get_contextvars() == {}


def test_bind_request_context_without_user() -> None:
    """``user_id`` is optional and must not appear when omitted."""
    app_logging.configure_logging("INFO")
    app_logging.bind_request_context("req-2")
    ctx = structlog.contextvars.get_contextvars()
    assert "user_id" not in ctx
    assert ctx.get("request_id") == "req-2"
    app_logging.clear_request_context()
