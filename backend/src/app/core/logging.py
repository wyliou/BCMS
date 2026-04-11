"""structlog configuration — JSON to stdout with ISO-8601 UTC timestamps.

Call :func:`configure_logging` once at app startup (from FastAPI lifespan).
Use :func:`bind_request_context` from middleware to inject ``request_id`` /
``user_id`` into the structlog contextvars so every subsequent log statement
produced during the request automatically carries them.
"""

from __future__ import annotations

import logging

import structlog

__all__ = ["configure_logging", "bind_request_context", "clear_request_context"]


_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def configure_logging(log_level: str = "INFO") -> None:
    """Install the structlog pipeline and bridge stdlib ``logging`` to it.

    Idempotent: calling multiple times with the same level is safe. Changing
    the level between calls updates the stdlib root logger level.

    Args:
        log_level: Level name — one of ``DEBUG``/``INFO``/``WARNING``/``ERROR``/
            ``CRITICAL``. ``WARN`` is accepted as an alias for ``WARNING``.

    Raises:
        ValueError: If ``log_level`` is not a recognized level name.
    """
    normalized = log_level.upper()
    if normalized == "WARN":
        normalized = "WARNING"
    if normalized not in _VALID_LEVELS:
        raise ValueError(f"Invalid log level: {log_level!r}")

    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    level_int = level_map[normalized]

    logging.basicConfig(
        level=level_int,
        format="%(message)s",
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_int),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def bind_request_context(request_id: str, user_id: str | None = None) -> None:
    """Bind request-scoped context vars for subsequent structlog events.

    Called from request-id middleware at the start of each request. The bound
    values appear as top-level fields on every log entry emitted within the
    same async task thanks to structlog's ``contextvars`` processor.

    Args:
        request_id: UUID string identifying the current HTTP request.
        user_id: Authenticated user's ID, if any. ``None`` for anonymous
            requests.
    """
    structlog.contextvars.clear_contextvars()
    values: dict[str, str] = {"request_id": request_id}
    if user_id is not None:
        values["user_id"] = user_id
    structlog.contextvars.bind_contextvars(**values)


def clear_request_context() -> None:
    """Clear the structlog context vars bound by :func:`bind_request_context`.

    Called from middleware on request completion so that log lines emitted
    outside a request scope (e.g. scheduler callbacks, worker loops) do not
    inherit stale IDs.
    """
    structlog.contextvars.clear_contextvars()
