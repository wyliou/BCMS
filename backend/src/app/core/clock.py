"""UTC clock seam.

`now_utc()` is the single injectable point for the current time in the application.
Tests patch this function (or `app.core.clock.now_utc`) instead of monkey-patching
`datetime.now` globally. No other module in `src/` is permitted to call
`datetime.now()` directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

__all__ = ["now_utc"]


def now_utc() -> datetime:
    """Return the current UTC time as a timezone-aware datetime.

    Returns:
        datetime: Current UTC datetime with ``tzinfo=timezone.utc``.
    """
    return datetime.now(tz=timezone.utc)
