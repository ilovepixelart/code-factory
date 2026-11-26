"""create checks tables

Revision ID: 5d8e2f4a6c13
Revises: 11430b1f7947
Create Date: 2026-11-23 18:10:00.000000

Schema only, nothing seeded: the database starts empty.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5d8e2f4a6c13"
down_revision: str | Sequence[str] | None = "11430b1f7947"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "check_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("commit", sa.Text(), nullable=False),
        sa.Column("tree_id", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("contained", sa.Text(), nullable=False),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("log_path", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("workspace", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.CheckConstraint(
            "scope IN ('fast', 'reached', 'full')", name=op.f("ck_check_runs_known_scope")
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'running', 'finished', 'lost')",
            name=op.f("ck_check_runs_known_state"),
        ),
        sa.CheckConstraint(
            "contained IN ('none', 'srt', 'container')",
            name=op.f("ck_check_runs_known_containment"),
        ),
        sa.CheckConstraint(
            "verdict IN ('passed', 'failed', 'no_verdict')",
            name=op.f("ck_check_runs_known_verdict"),
        ),
        sa.CheckConstraint(
            "(state = 'finished') = (verdict IS NOT NULL)",
            name=op.f("ck_check_runs_verdict_when_finished"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_check_runs")),
    )
    op.create_index(
        "ix_check_runs_one_active_per_subject",
        "check_runs",
        ["repository", "subject"],
        unique=True,
        postgresql_where=sa.text("state IN ('queued', 'running')"),
    )
    op.create_index(
        "ix_check_runs_subject_newest",
        "check_runs",
        ["repository", "subject", sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_index("ix_check_runs_state_beat_at", "check_runs", ["state", "beat_at"])
    op.create_table(
        "check_main_records",
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("commit", sa.Text(), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=False),
        sa.Column("log_path", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("step", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("passed", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("broken_by", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("searched", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("reason", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.CheckConstraint(
            "exit_code > -1000", name=op.f("ck_check_main_records_exit_code_plausible")
        ),
        sa.PrimaryKeyConstraint("repository", name=op.f("pk_check_main_records")),
    )
    op.create_table(
        "check_claims",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("head", sa.Text(), nullable=False),
        sa.Column("holder", sa.Text(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_check_claims")),
        sa.UniqueConstraint(
            "repository", "subject", "head", name=op.f("uq_check_claims_one_claim_per_head")
        ),
    )
    op.create_table(
        "check_offers",
        sa.Column("runner", sa.Text(), nullable=False),
        sa.Column("repositories", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("runner", name=op.f("pk_check_offers")),
    )
    op.create_table(
        "check_declines",
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("head", sa.Text(), nullable=False),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("repository", "subject", "head", name=op.f("pk_check_declines")),
    )
    op.create_index("ix_check_declines_declined_at", "check_declines", ["declined_at"])
    op.create_table(
        "check_verify_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("release", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=False),
        sa.Column("log_path", sa.Text(), nullable=False),
        sa.Column("ticket_id", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_check_verify_runs")),
    )
    op.create_index("ix_check_verify_runs_repository_id", "check_verify_runs", ["repository", "id"])


def downgrade() -> None:
    op.drop_index("ix_check_verify_runs_repository_id", table_name="check_verify_runs")
    op.drop_table("check_verify_runs")
    op.drop_index("ix_check_declines_declined_at", table_name="check_declines")
    op.drop_table("check_declines")
    op.drop_table("check_offers")
    op.drop_table("check_claims")
    op.drop_table("check_main_records")
    op.drop_index("ix_check_runs_state_beat_at", table_name="check_runs")
    op.drop_index("ix_check_runs_subject_newest", table_name="check_runs")
    op.drop_index("ix_check_runs_one_active_per_subject", table_name="check_runs")
    op.drop_table("check_runs")
