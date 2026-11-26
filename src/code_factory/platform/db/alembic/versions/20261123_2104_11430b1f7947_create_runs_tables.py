"""create runs tables

Revision ID: 11430b1f7947
Revises: 0e61c4b87707
Create Date: 2026-11-23 21:04:25.459656

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "11430b1f7947"
down_revision: str | Sequence[str] | None = "0e61c4b87707"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nothing is imported: runs start empty. The model requests of a run (`session_run_requests`)
    # and the memory entries it was given (`memory_deliveries`) stay in the modules that own them,
    # which name a run by id with no foreign key.
    op.create_table(
        "agent_halt",
        sa.Column("id", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("halted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("by", sa.Text(), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_agent_halt_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_halt")),
    )
    op.create_table(
        "permission_decisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("ticket_key", sa.Text(), nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("by", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.CheckConstraint(
            "by IN ('policy', 'reviewer', 'owner')",
            name=op.f("ck_permission_decisions_known_decider"),
        ),
        sa.CheckConstraint(
            "decision IN ('allow', 'deny')", name=op.f("ck_permission_decisions_known_decision")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permission_decisions")),
    )
    op.create_index(
        "ix_permission_decisions_ticket_latest",
        "permission_decisions",
        ["repository", "ticket_key", sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_table(
        "permission_reviews",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("ticket_key", sa.Text(), nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("input_sha256", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "verdict IN ('allow', 'deny', 'owner')",
            name=op.f("ck_permission_reviews_known_verdict"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permission_reviews")),
    )
    op.create_index(
        "ix_permission_reviews_session", "permission_reviews", ["session_id"], unique=False
    )
    op.create_table(
        "permission_rules",
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("adopted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("kind", name=op.f("pk_permission_rules")),
    )
    op.create_table(
        "run_previews",
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("pgid", sa.BigInteger(), nullable=False),
        sa.Column("pgid_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("pgid > 1", name=op.f("ck_run_previews_pgid_above_one")),
        sa.CheckConstraint(
            "port BETWEEN 1024 AND 65535", name=op.f("ck_run_previews_port_unprivileged")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.number"],
            name=op.f("fk_run_previews_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_id", name=op.f("pk_run_previews")),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=True),
        sa.Column("ticket_key", sa.Text(), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("branch", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("worktree", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("log", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("pid", sa.BigInteger(), nullable=True),
        sa.Column("pid_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("awake_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("looping", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "permissions", sa.Text(), server_default=sa.text("'acceptEdits'"), nullable=False
        ),
        sa.Column("iteration", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("continued", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cost", sa.Numeric(precision=14, scale=6), nullable=True),
        sa.Column("cost_estimated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("tokens", sa.BigInteger(), nullable=True),
        sa.Column("cache_read", sa.BigInteger(), nullable=True),
        sa.Column("turns", sa.Integer(), nullable=True),
        sa.Column("halted", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("instructions", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("model", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("agent", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("connection", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("head", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("judged_head", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("tests_checked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("uncommitted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("commits", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("limited_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resume_refused", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("context", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("context_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("memory_digest", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "permissions IN ('acceptEdits', 'bypassPermissions')", name=op.f("ck_runs_known_mode")
        ),
        sa.CheckConstraint(
            "stage IN ('spec', 'build', 'review', 'split', 'coordinate')",
            name=op.f("ck_runs_known_stage"),
        ),
        sa.CheckConstraint("attempt >= 0", name=op.f("ck_runs_attempt_not_negative")),
        sa.CheckConstraint("iteration >= 1", name=op.f("ck_runs_iteration_from_one")),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.number"],
            name=op.f("fk_runs_ticket_id_tickets"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
    )
    op.create_index(
        "ix_runs_active",
        "runs",
        ["id"],
        unique=False,
        postgresql_where=sa.text("exit_code IS NULL"),
    )
    op.create_index(
        "ix_runs_agent_started",
        "runs",
        ["agent", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_index("ix_runs_started_at", "runs", ["started_at"], unique=False)
    op.create_index(
        "ix_runs_ticket_started",
        "runs",
        ["ticket_id", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_runs_unsettled",
        "runs",
        ["settled_at"],
        unique=False,
        postgresql_where=sa.text("exit_code IS NOT NULL AND settled_at IS NULL"),
    )
    op.create_index(
        "uq_runs_active_coordinator",
        "runs",
        ["repository"],
        unique=True,
        postgresql_where=sa.text("stage = 'coordinate' AND exit_code IS NULL"),
    )
    op.create_index(
        "uq_runs_active_ticket_attempt",
        "runs",
        ["ticket_id", "attempt"],
        unique=True,
        postgresql_where=sa.text("exit_code IS NULL AND ticket_id IS NOT NULL"),
    )
    op.create_table(
        "permission_requests",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("ticket_key", sa.Text(), nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_by", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.CheckConstraint(
            "id ~ '^[0-9a-f]{12}$'", name=op.f("ck_permission_requests_id_is_12_hex")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'answered', 'expired', 'withdrawn')",
            name=op.f("ck_permission_requests_known_status"),
        ),
        sa.CheckConstraint(
            "verdict IS NULL OR verdict IN ('allow', 'deny')",
            name=op.f("ck_permission_requests_known_verdict"),
        ),
        sa.CheckConstraint(
            "char_length(summary) <= 300", name=op.f("ck_permission_requests_summary_at_most_300")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name=op.f("fk_permission_requests_run_id_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permission_requests")),
    )
    op.create_index(
        "ix_permission_requests_answered_kind",
        "permission_requests",
        ["kind"],
        unique=False,
        postgresql_where=sa.text("status = 'answered'"),
    )
    op.create_index(
        op.f("ix_permission_requests_run_id"), "permission_requests", ["run_id"], unique=False
    )
    op.create_index(
        "ix_permission_requests_status_requested",
        "permission_requests",
        ["status", "requested_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_permission_requests_status_requested", table_name="permission_requests")
    op.drop_index(op.f("ix_permission_requests_run_id"), table_name="permission_requests")
    op.drop_index(
        "ix_permission_requests_answered_kind",
        table_name="permission_requests",
        postgresql_where=sa.text("status = 'answered'"),
    )
    op.drop_table("permission_requests")
    op.drop_index(
        "uq_runs_active_ticket_attempt",
        table_name="runs",
        postgresql_where=sa.text("exit_code IS NULL AND ticket_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_runs_active_coordinator",
        table_name="runs",
        postgresql_where=sa.text("stage = 'coordinate' AND exit_code IS NULL"),
    )
    op.drop_index(
        "ix_runs_unsettled",
        table_name="runs",
        postgresql_where=sa.text("exit_code IS NOT NULL AND settled_at IS NULL"),
    )
    op.drop_index("ix_runs_ticket_started", table_name="runs")
    op.drop_index("ix_runs_started_at", table_name="runs")
    op.drop_index("ix_runs_agent_started", table_name="runs")
    op.drop_index(
        "ix_runs_active", table_name="runs", postgresql_where=sa.text("exit_code IS NULL")
    )
    op.drop_table("runs")
    op.drop_table("run_previews")
    op.drop_table("permission_rules")
    op.drop_index("ix_permission_reviews_session", table_name="permission_reviews")
    op.drop_table("permission_reviews")
    op.drop_index("ix_permission_decisions_ticket_latest", table_name="permission_decisions")
    op.drop_table("permission_decisions")
    op.drop_table("agent_halt")
