"""Add ``org_units.excluded_for_cycle_ids`` JSONB column (FR-002).

Batch 0's baseline predates the Batch 2 decision to ship the
per-cycle filing-unit exclusion decision on the ``org_units`` row
itself. This migration adds the column as a non-null JSONB defaulting
to the empty JSON array.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the ``excluded_for_cycle_ids`` column to ``org_units``."""
    op.add_column(
        "org_units",
        sa.Column(
            "excluded_for_cycle_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    """Drop the column created by :func:`upgrade`."""
    op.drop_column("org_units", "excluded_for_cycle_ids")
