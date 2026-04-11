"""Baseline schema — every table from architecture §6.

Revision ID: 0001
Revises:
Create Date: 2026-04-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ENUMS: list[tuple[str, tuple[str, ...]]] = [
    ("cycle_status", ("draft", "open", "closed")),
    ("upload_status", ("pending", "valid", "invalid")),
    (
        "notification_type",
        (
            "cycle_opened",
            "upload_confirmed",
            "resubmit_requested",
            "deadline_reminder",
            "personnel_imported",
            "shared_cost_imported",
        ),
    ),
    ("notification_status", ("queued", "sent", "failed", "bounced")),
    ("notification_channel", ("email",)),
    ("account_category", ("operational", "personnel", "shared_cost")),
    (
        "org_level_code",
        ("0000", "0500", "0800", "1000", "2000", "4000", "5000", "6000"),
    ),
    ("job_status", ("queued", "running", "succeeded", "failed")),
]


def _create_enums() -> None:
    """Create all PostgreSQL enum types used by the baseline schema."""
    for name, values in _ENUMS:
        sa.Enum(*values, name=name, create_type=True).create(op.get_bind(), checkfirst=True)


def _drop_enums() -> None:
    """Drop all PostgreSQL enum types in reverse creation order."""
    for name, values in reversed(_ENUMS):
        sa.Enum(*values, name=name, create_type=True).drop(op.get_bind(), checkfirst=True)


def _pg_enum(name: str, *values: str) -> postgresql.ENUM:
    """Return a ``postgresql.ENUM`` bound to an already-created type.

    The enum types are created once in :func:`_create_enums`; column
    declarations reuse the same name with ``create_type=False`` so Alembic
    does not try to re-create them.

    Args:
        name: Enum type name.
        *values: Enum member values.

    Returns:
        postgresql.ENUM: Column type referencing the existing Postgres enum.
    """
    return postgresql.ENUM(*values, name=name, create_type=False)


def _create_updated_at_function() -> None:
    """Install the shared ``set_updated_at`` trigger function."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = NOW();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def _attach_updated_at_triggers(tables: list[str]) -> None:
    """Attach a ``BEFORE UPDATE`` trigger to each listed table.

    Args:
        tables: Table names that carry an ``updated_at`` column.
    """
    for table in tables:
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )


def _drop_updated_at_triggers(tables: list[str]) -> None:
    """Drop triggers created by :func:`_attach_updated_at_triggers`.

    Args:
        tables: Tables to detach.
    """
    for table in tables:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated ON {table};")


def upgrade() -> None:
    """Create every BCMS table, enum, index, and trigger from a clean slate."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    _create_updated_at_function()
    _create_enums()

    # ---------- org_units ------------------------------------------------
    op.create_table(
        "org_units",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "level_code",
            _pg_enum("org_level_code", "0000", "0500", "0800", "1000", "2000", "4000", "5000", "6000"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org_units.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("is_filing_unit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "is_reviewer_only", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "NOT (is_filing_unit AND is_reviewer_only)",
            name="org_units_filing_xor_reviewer",
        ),
    )
    op.create_index("idx_org_units_parent", "org_units", ["parent_id"])
    op.execute(
        "CREATE INDEX idx_org_units_filing ON org_units (is_filing_unit) "
        "WHERE is_filing_unit;"
    )

    # ---------- users ----------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("sso_id_enc", sa.LargeBinary(), nullable=False),
        sa.Column("sso_id_hash", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email_enc", sa.LargeBinary(), nullable=False),
        sa.Column("email_hash", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column(
            "roles",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "org_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org_units.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
    )
    op.create_index("idx_users_org_unit", "users", ["org_unit_id"])
    op.execute("CREATE INDEX idx_users_roles_gin ON users USING gin (roles);")

    # ---------- sessions -------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("refresh_token_hash", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
    )
    op.create_index("idx_sessions_user", "sessions", ["user_id"])
    op.execute(
        "CREATE INDEX idx_sessions_active ON sessions (absolute_expires_at) "
        "WHERE revoked_at IS NULL;"
    )

    # ---------- account_codes -------------------------------------------
    op.create_table(
        "account_codes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "category",
            _pg_enum("account_category", "operational", "personnel", "shared_cost"),
            nullable=False,
        ),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
        sa.CheckConstraint("level >= 1", name="account_codes_level_positive"),
    )
    op.execute(
        "CREATE INDEX idx_account_codes_category ON account_codes (category) WHERE is_active;"
    )

    # ---------- budget_cycles -------------------------------------------
    op.create_table(
        "budget_cycles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column(
            "reporting_currency",
            sa.CHAR(3),
            nullable=False,
            server_default=sa.text("'TWD'"),
        ),
        sa.Column(
            "status",
            _pg_enum("cycle_status", "draft", "open", "closed"),
            nullable=False,
            server_default=sa.text("'draft'::cycle_status"),
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "closed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("reopen_reason", sa.Text(), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_budget_cycles_active_year ON budget_cycles (fiscal_year) "
        "WHERE status IN ('draft', 'open');"
    )
    op.create_index("idx_budget_cycles_status", "budget_cycles", ["status"])

    # ---------- cycle_reminder_schedules --------------------------------
    op.create_table(
        "cycle_reminder_schedules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "cycle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budget_cycles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("days_before", sa.Integer(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
        sa.UniqueConstraint("cycle_id", "days_before", name="uq_cycle_reminder_days"),
        sa.CheckConstraint("days_before > 0", name="cycle_reminder_days_positive"),
    )
    op.create_index("idx_reminder_schedules_cycle", "cycle_reminder_schedules", ["cycle_id"])

    # ---------- actual_expenses -----------------------------------------
    op.create_table(
        "actual_expenses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "cycle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budget_cycles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "org_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org_units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "account_code_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account_codes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "imported_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
        sa.UniqueConstraint(
            "cycle_id",
            "org_unit_id",
            "account_code_id",
            name="uq_actual_expenses_cycle_org_account",
        ),
    )
    op.create_index(
        "idx_actuals_cycle_org",
        "actual_expenses",
        ["cycle_id", "org_unit_id"],
    )

    # ---------- excel_templates -----------------------------------------
    op.create_table(
        "excel_templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "cycle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budget_cycles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org_units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("file_path_enc", sa.LargeBinary(), nullable=False),
        sa.Column("file_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "generated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("generation_error", sa.Text(), nullable=True),
        sa.UniqueConstraint("cycle_id", "org_unit_id", name="uq_templates_cycle_org"),
    )
    op.create_index("idx_templates_cycle", "excel_templates", ["cycle_id"])

    # ---------- budget_uploads ------------------------------------------
    op.create_table(
        "budget_uploads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "cycle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budget_cycles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "org_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org_units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "uploader_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("file_path_enc", sa.LargeBinary(), nullable=False),
        sa.Column("file_hash", sa.LargeBinary(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            _pg_enum("upload_status", "pending", "valid", "invalid"),
            nullable=False,
            server_default=sa.text("'valid'::upload_status"),
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "cycle_id", "org_unit_id", "version", name="uq_budget_uploads_cycle_org_version"
        ),
        sa.CheckConstraint(
            "file_size_bytes <= 10485760", name="budget_uploads_size_limit"
        ),
        sa.CheckConstraint("row_count <= 5000", name="budget_uploads_row_limit"),
    )
    op.execute(
        "CREATE INDEX idx_budget_uploads_cycle_unit ON budget_uploads "
        "(cycle_id, org_unit_id, version DESC);"
    )
    op.execute(
        "CREATE INDEX idx_budget_uploads_latest ON budget_uploads "
        "(cycle_id, org_unit_id, uploaded_at DESC);"
    )

    op.create_table(
        "budget_lines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "upload_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budget_uploads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_code_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account_codes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.UniqueConstraint("upload_id", "account_code_id", name="uq_budget_lines_upload_account"),
        sa.CheckConstraint("amount >= 0", name="budget_lines_amount_nonneg"),
    )
    op.create_index("idx_budget_lines_upload", "budget_lines", ["upload_id"])
    op.create_index("idx_budget_lines_account", "budget_lines", ["account_code_id"])

    # ---------- personnel ------------------------------------------------
    op.create_table(
        "personnel_budget_uploads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "cycle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budget_cycles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "uploader_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("file_path_enc", sa.LargeBinary(), nullable=False),
        sa.Column("file_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "status",
            _pg_enum("upload_status", "pending", "valid", "invalid"),
            nullable=False,
            server_default=sa.text("'valid'::upload_status"),
        ),
        sa.Column("affected_org_units_summary", postgresql.JSONB(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("cycle_id", "version", name="uq_personnel_uploads_cycle_version"),
    )
    op.execute(
        "CREATE INDEX idx_personnel_uploads_cycle ON personnel_budget_uploads "
        "(cycle_id, version DESC);"
    )

    op.create_table(
        "personnel_budget_lines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "upload_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("personnel_budget_uploads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org_units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "account_code_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account_codes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.UniqueConstraint(
            "upload_id",
            "org_unit_id",
            "account_code_id",
            name="uq_personnel_lines_upload_org_account",
        ),
        sa.CheckConstraint("amount > 0", name="personnel_lines_amount_positive"),
    )
    op.create_index("idx_personnel_lines_upload", "personnel_budget_lines", ["upload_id"])
    op.create_index("idx_personnel_lines_org", "personnel_budget_lines", ["org_unit_id"])

    # ---------- shared cost ---------------------------------------------
    op.create_table(
        "shared_cost_uploads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "cycle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budget_cycles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "uploader_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("file_path_enc", sa.LargeBinary(), nullable=False),
        sa.Column("file_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "status",
            _pg_enum("upload_status", "pending", "valid", "invalid"),
            nullable=False,
            server_default=sa.text("'valid'::upload_status"),
        ),
        sa.Column("affected_org_units_summary", postgresql.JSONB(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("cycle_id", "version", name="uq_shared_uploads_cycle_version"),
    )
    op.execute(
        "CREATE INDEX idx_shared_uploads_cycle ON shared_cost_uploads (cycle_id, version DESC);"
    )

    op.create_table(
        "shared_cost_lines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "upload_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shared_cost_uploads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org_units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "account_code_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account_codes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.UniqueConstraint(
            "upload_id",
            "org_unit_id",
            "account_code_id",
            name="uq_shared_lines_upload_org_account",
        ),
        sa.CheckConstraint("amount > 0", name="shared_lines_amount_positive"),
    )
    op.create_index("idx_shared_lines_upload", "shared_cost_lines", ["upload_id"])
    op.create_index("idx_shared_lines_org", "shared_cost_lines", ["org_unit_id"])

    # ---------- resubmit_requests ---------------------------------------
    op.create_table(
        "resubmit_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "cycle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budget_cycles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "org_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("org_units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "requester_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("target_version", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.execute(
        "CREATE INDEX idx_resubmit_cycle_org ON resubmit_requests "
        "(cycle_id, org_unit_id, requested_at DESC);"
    )

    # ---------- notifications -------------------------------------------
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "recipient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "type",
            _pg_enum(
                "notification_type",
                "cycle_opened",
                "upload_confirmed",
                "resubmit_requested",
                "deadline_reminder",
                "personnel_imported",
                "shared_cost_imported",
            ),
            nullable=False,
        ),
        sa.Column(
            "channel",
            _pg_enum("notification_channel", "email"),
            nullable=False,
            server_default=sa.text("'email'::notification_channel"),
        ),
        sa.Column(
            "status",
            _pg_enum(
                "notification_status", "queued", "sent", "failed", "bounced"
            ),
            nullable=False,
            server_default=sa.text("'queued'::notification_status"),
        ),
        sa.Column("related_resource_type", sa.String(64), nullable=True),
        sa.Column(
            "related_resource_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("link_url", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("body_excerpt", sa.Text(), nullable=True),
        sa.Column("bounce_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "CREATE INDEX idx_notifications_recipient ON notifications "
        "(recipient_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX idx_notifications_status ON notifications (status) "
        "WHERE status IN ('queued','failed','bounced');"
    )

    # ---------- audit_logs ----------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "sequence_no",
            sa.BigInteger(),
            nullable=False,
            unique=True,
            autoincrement=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("prev_hash", sa.LargeBinary(), nullable=False),
        sa.Column("hash_chain_value", sa.LargeBinary(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "idx_audit_user", "audit_logs", ["user_id", sa.text("occurred_at DESC")]
    )
    op.create_index(
        "idx_audit_action", "audit_logs", ["action", sa.text("occurred_at DESC")]
    )
    op.create_index(
        "idx_audit_resource", "audit_logs", ["resource_type", "resource_id"]
    )
    op.create_index("idx_audit_occurred", "audit_logs", ["occurred_at"])
    op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC")

    # ---------- job_runs ------------------------------------------------
    op.create_table(
        "job_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column(
            "status",
            _pg_enum("job_status", "queued", "running", "succeeded", "failed"),
            nullable=False,
            server_default=sa.text("'queued'::job_status"),
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("result_file_path_enc", sa.LargeBinary(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "enqueued_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "enqueued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("worker_id", sa.String(128), nullable=True),
    )
    op.execute(
        "CREATE INDEX idx_job_runs_queue ON job_runs (status, enqueued_at) "
        "WHERE status = 'queued';"
    )
    op.create_index(
        "idx_job_runs_user", "job_runs", ["enqueued_by", sa.text("enqueued_at DESC")]
    )

    # ---------- updated_at triggers -------------------------------------
    _attach_updated_at_triggers(
        [
            "org_units",
            "users",
            "account_codes",
            "budget_cycles",
            "actual_expenses",
        ]
    )


def downgrade() -> None:
    """Drop every object created by :func:`upgrade` in reverse order."""
    _drop_updated_at_triggers(
        [
            "actual_expenses",
            "budget_cycles",
            "account_codes",
            "users",
            "org_units",
        ]
    )
    op.drop_table("job_runs")
    op.drop_table("audit_logs")
    op.drop_table("notifications")
    op.drop_table("resubmit_requests")
    op.drop_table("shared_cost_lines")
    op.drop_table("shared_cost_uploads")
    op.drop_table("personnel_budget_lines")
    op.drop_table("personnel_budget_uploads")
    op.drop_table("budget_lines")
    op.drop_table("budget_uploads")
    op.drop_table("excel_templates")
    op.drop_table("actual_expenses")
    op.drop_table("cycle_reminder_schedules")
    op.execute("DROP INDEX IF EXISTS uq_budget_cycles_active_year")
    op.drop_table("budget_cycles")
    op.drop_table("account_codes")
    op.drop_table("sessions")
    op.drop_table("users")
    op.drop_table("org_units")
    _drop_enums()
    op.execute("DROP FUNCTION IF EXISTS set_updated_at() CASCADE")
