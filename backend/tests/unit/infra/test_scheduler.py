"""Unit tests for :mod:`app.infra.scheduler`."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.infra import scheduler as scheduler_module


@pytest.fixture(autouse=True)
def _reset_scheduler() -> Iterator[None]:
    """Ensure each test starts and ends with a fresh scheduler instance."""
    scheduler_module.shutdown()
    yield
    scheduler_module.shutdown()


def test_register_cron_adds_job() -> None:
    """Registering a cron creates an APScheduler job row."""

    def _noop() -> None:
        return None

    scheduler_module.register_cron("0 9 * * *", _noop, name="daily")
    scheduler_module.start()
    try:
        jobs = scheduler_module.get_scheduler().get_jobs()
        assert any(job.id == "daily" for job in jobs)
    finally:
        scheduler_module.shutdown()


def test_register_cron_idempotent() -> None:
    """Registering the same name twice replaces the existing job."""
    scheduler_module.register_cron("0 9 * * *", lambda: None, name="daily")
    scheduler_module.register_cron("0 10 * * *", lambda: None, name="daily")
    scheduler_module.start()
    try:
        jobs = scheduler_module.get_scheduler().get_jobs()
        assert sum(1 for job in jobs if job.id == "daily") == 1
    finally:
        scheduler_module.shutdown()


def test_scheduler_timezone_matches_settings() -> None:
    """The scheduler timezone comes from :attr:`Settings.timezone`."""
    tz = str(scheduler_module.get_scheduler().timezone)
    assert tz == "Asia/Taipei"


def test_shutdown_is_idempotent() -> None:
    """Calling :func:`shutdown` multiple times does not raise."""
    scheduler_module.shutdown()
    scheduler_module.shutdown()


async def test_callback_exception_isolation(caplog: pytest.LogCaptureFixture) -> None:
    """An exception inside the callback is caught and logged, not re-raised."""

    async def _boom() -> None:
        raise RuntimeError("kaboom")

    wrapped = scheduler_module._wrap_callable(_boom, "failing")
    # Should NOT raise
    await wrapped()


def test_register_cron_invalid_expression_raises() -> None:
    """APScheduler rejects malformed cron expressions."""
    with pytest.raises(ValueError):
        scheduler_module.register_cron("not a cron", lambda: None, name="bad")


async def test_sync_callback_wrapped() -> None:
    """Synchronous callbacks are also isolated."""
    called: list[bool] = []

    def _ok() -> None:
        called.append(True)

    wrapped = scheduler_module._wrap_callable(_ok, "ok")
    await wrapped()
    assert called == [True]
