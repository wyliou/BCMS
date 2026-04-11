"""APScheduler wrapper — cron-only.

Registers async callbacks against :class:`apscheduler.schedulers.asyncio.AsyncIOScheduler`
with the timezone derived from :attr:`Settings.timezone` (CR-038). Every
registered callback is wrapped in a try/except so a single failure cannot take
down the scheduler thread (CR-035).
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings

__all__ = [
    "register_cron",
    "get_scheduler",
    "start",
    "shutdown",
]


_LOG = structlog.get_logger(__name__)
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Return the module-level :class:`AsyncIOScheduler`, creating it on demand.

    Returns:
        AsyncIOScheduler: The shared scheduler instance.
    """
    global _scheduler
    if _scheduler is None:
        tz = ZoneInfo(get_settings().timezone)
        _scheduler = AsyncIOScheduler(timezone=tz)
    return _scheduler


def _wrap_callable(
    func: Callable[..., Any | Awaitable[Any]],
    name: str,
) -> Callable[[], Awaitable[None]]:
    """Wrap ``func`` in an async try/except that logs and swallows exceptions.

    The inner callable can be sync or async; both are supported. Exceptions
    are caught with a broad ``except Exception`` — this is one of the few
    places the ``Subagent Constraints`` allow it, because the scheduler's
    event loop thread must not crash (CR-035).

    Args:
        func: User-supplied callback.
        name: Job name (for logging).

    Returns:
        Callable[[], Awaitable[None]]: Coroutine function for APScheduler.
    """

    async def _runner() -> None:
        try:
            result = func()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            _LOG.error("scheduler.callback_failed", job=name, error=str(exc))

    _runner.__name__ = f"{name}_wrapped"
    return _runner


def register_cron(
    expr: str,
    func: Callable[..., Any | Awaitable[Any]],
    name: str,
) -> None:
    """Register a cron-triggered callback.

    Idempotent: calling with the same ``name`` replaces the existing job.

    Args:
        expr: Cron expression (5-field: ``minute hour dom month dow``).
        func: Sync or async callable with no required arguments.
        name: Unique job name used as the APScheduler job id.

    Raises:
        ValueError: If ``expr`` is not a valid cron expression.
    """
    scheduler = get_scheduler()
    tz = ZoneInfo(get_settings().timezone)
    trigger = CronTrigger.from_crontab(expr, timezone=tz)
    wrapped = _wrap_callable(func, name)
    scheduler.add_job(wrapped, trigger=trigger, id=name, replace_existing=True)


def start() -> None:
    """Start the scheduler if it is not already running.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()


def shutdown() -> None:
    """Shut the scheduler down gracefully and drop the module-level handle.

    Waits for running jobs to complete (``wait=True``). Idempotent.
    """
    global _scheduler
    if _scheduler is None:
        return
    if _scheduler.running:
        _scheduler.shutdown(wait=True)
    _scheduler = None
