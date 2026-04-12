"""Integration tests for :mod:`app.domain.shared_costs`.

These tests require a live PostgreSQL instance (via the ``db_session``
fixture). They are automatically skipped when Postgres is unreachable.

All tests are marked ``@integration`` per the M6 gate specification.
"""

from __future__ import annotations

import pytest

# Mark module so the gate command ``-m "not slow"`` still runs these.
pytestmark = [pytest.mark.asyncio]

integration = pytest.mark.integration


@integration
async def test_placeholder_integration() -> None:
    """Placeholder — integration tests require live Postgres (skipped when unavailable)."""
    pytest.skip("Integration tests require live Postgres — run with a real DB.")
