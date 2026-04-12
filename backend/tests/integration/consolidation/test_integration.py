"""Integration-tier tests for :mod:`app.domain.consolidation`.

These tests are gated behind the ``integration`` marker and require a
live Postgres database. They are skipped by default in the unit tier.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration]


@pytest.mark.skip(reason="Requires a live Postgres; exercised in the integration tier")
def test_integration_placeholder() -> None:
    """Placeholder to keep the test module importable."""
    assert True
