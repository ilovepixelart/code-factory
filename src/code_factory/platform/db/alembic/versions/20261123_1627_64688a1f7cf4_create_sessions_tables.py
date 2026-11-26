"""create sessions tables

Revision ID: 64688a1f7cf4
Revises: c4eeb52f29c7
Create Date: 2026-11-23 16:27:04.903925

Schema only, nothing seeded. The ledger tables are rebuilt from the capture spool and the views
from the ledger, so none of them has a foreign key.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "64688a1f7cf4"
down_revision: str | Sequence[str] | None = "c4eeb52f29c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_events",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=True),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("spool", sa.Text(), nullable=False),
        sa.Column("spool_offset", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("seq", name=op.f("pk_session_events")),
        sa.UniqueConstraint("spool", "spool_offset", name="uq_session_events_spool_spool_offset"),
    )
    op.create_index(
        "ix_session_events_session_id_seq", "session_events", ["session_id", "seq"], unique=False
    )
    op.create_table(
        "session_rejects",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("spool", sa.Text(), nullable=False),
        sa.Column("spool_offset", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("head", sa.Text(), nullable=False),
        sa.Column(
            "rejected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("seq", name=op.f("pk_session_rejects")),
        sa.UniqueConstraint("spool", "spool_offset", name="uq_session_rejects_spool_spool_offset"),
    )
    op.create_table(
        "session_run_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column(
            "reported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("input_tokens >= 0", name=op.f("ck_session_run_requests_input_tokens")),
        sa.CheckConstraint(
            "output_tokens >= 0", name=op.f("ck_session_run_requests_output_tokens")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_run_requests")),
    )
    op.create_index(
        "ix_session_run_requests_run_id", "session_run_requests", ["run_id"], unique=False
    )
    op.create_table(
        "session_spool_progress",
        sa.Column("spool", sa.Text(), nullable=False),
        sa.Column("byte_offset", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("byte_offset >= 0", name=op.f("ck_session_spool_progress_byte_offset")),
        sa.PrimaryKeyConstraint("spool", name=op.f("pk_session_spool_progress")),
    )
    op.create_table(
        "session_views",
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seq", sa.BigInteger(), nullable=False),
        sa.Column("window_seq", sa.BigInteger(), nullable=False),
        sa.Column("cwd", sa.Text(), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("branch", sa.Text(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("rules_version", sa.Integer(), nullable=False),
        sa.Column("view", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_session_views")),
    )
    op.create_index(
        "ix_session_views_last_event_at",
        "session_views",
        [sa.text("last_event_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_session_views_state_last_event_at",
        "session_views",
        ["state", "last_event_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_session_views_state_last_event_at", table_name="session_views")
    op.drop_index("ix_session_views_last_event_at", table_name="session_views")
    op.drop_table("session_views")
    op.drop_table("session_spool_progress")
    op.drop_index("ix_session_run_requests_run_id", table_name="session_run_requests")
    op.drop_table("session_run_requests")
    op.drop_table("session_rejects")
    op.drop_index("ix_session_events_session_id_seq", table_name="session_events")
    op.drop_table("session_events")
