"""Unit tests for :mod:`app.core.clock`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core import clock


def test_now_utc_is_timezone_aware() -> None:
    """The returned datetime must carry a ``tzinfo``."""
    value = clock.now_utc()
    assert value.tzinfo is not None


def test_now_utc_is_utc() -> None:
    """The returned datetime must be anchored to UTC."""
    value = clock.now_utc()
    assert value.utcoffset() == datetime(1970, 1, 1, tzinfo=timezone.utc).utcoffset()


def test_now_utc_advances() -> None:
    """Two successive calls must be non-decreasing."""
    first = clock.now_utc()
    second = clock.now_utc()
    assert second >= first


def test_now_utc_is_patchable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests should be able to pin ``now_utc`` via ``monkeypatch.setattr``."""
    fixed = datetime(2026, 4, 12, 9, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(clock, "now_utc", lambda: fixed)
    assert clock.now_utc() == fixed


def test_now_utc_returns_datetime_type() -> None:
    """The return type must be :class:`datetime`."""
    assert isinstance(clock.now_utc(), datetime)
