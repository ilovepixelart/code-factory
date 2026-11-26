"""create stages tables

Revision ID: 171d2f76f64e
Revises: 46c9b8926d6f
Create Date: 2026-11-23 16:49:24.765561

Schema only, nothing seeded: the previous implementation's state is not carried over.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "171d2f76f64e"
down_revision: str | Sequence[str] | None = "46c9b8926d6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_changes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "stage IN ('spec', 'build', 'review', 'merged', 'released')",
            name=op.f("ck_evidence_changes_known_stage"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_evidence_changes_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_changes")),
    )
    op.create_index(
        op.f("ix_evidence_changes_ticket_stage"),
        "evidence_changes",
        ["ticket_number", "stage", sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_table(
        "fix_halts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("head", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("rounds", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rounds >= 0", name=op.f("ck_fix_halts_rounds_not_negative")),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_fix_halts_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fix_halts")),
        sa.UniqueConstraint(
            "ticket_number", "head", "reason", name=op.f("uq_fix_halts_halt_recorded")
        ),
    )
    op.create_index(
        op.f("ix_fix_halts_ticket_number"), "fix_halts", ["ticket_number"], unique=False
    )
    op.create_table(
        "fix_rounds",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("head", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("review", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("run_id", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reason IN ('ci', 'review', 'conflict')", name=op.f("ck_fix_rounds_known_reason")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_fix_rounds_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fix_rounds")),
        sa.UniqueConstraint(
            "ticket_number", "reason", "head", "review", name=op.f("uq_fix_rounds_round_given")
        ),
    )
    op.create_index(
        op.f("ix_fix_rounds_ticket_number"), "fix_rounds", ["ticket_number"], unique=False
    )
    op.create_table(
        "fix_waits",
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("head", sa.Text(), nullable=False),
        sa.Column("step", sa.Text(), nullable=False),
        sa.Column("main_commit", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_fix_waits_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_number", "head", name=op.f("pk_fix_waits")),
    )
    op.create_table(
        "review_verdicts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("head", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("reason", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("note", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('passed', 'returned', 'skipped')",
            name=op.f("ck_review_verdicts_known_outcome"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_review_verdicts_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_verdicts")),
    )
    op.create_index(
        op.f("ix_review_verdicts_ticket_id"),
        "review_verdicts",
        ["ticket_number", "id"],
        unique=False,
    )
    op.create_table(
        "stage_declarations",
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("by", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "stage IN ('spec', 'build', 'review', 'merged', 'released')",
            name=op.f("ck_stage_declarations_known_stage"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_stage_declarations_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_number", name=op.f("pk_stage_declarations")),
    )
    op.create_table(
        "stage_facts",
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("branch", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("known", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("local", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("pushed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("in_worktree", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("merged", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("has_commits", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("untraced", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("default_branch", sa.Text(), server_default=sa.text("'main'"), nullable=False),
        sa.Column("head", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_stage_facts_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_number", name=op.f("pk_stage_facts")),
    )
    op.create_index(
        op.f("ix_stage_facts_observed_at"), "stage_facts", ["observed_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_stage_facts_observed_at"), table_name="stage_facts")
    op.drop_table("stage_facts")
    op.drop_table("stage_declarations")
    op.drop_index(op.f("ix_review_verdicts_ticket_id"), table_name="review_verdicts")
    op.drop_table("review_verdicts")
    op.drop_table("fix_waits")
    op.drop_index(op.f("ix_fix_rounds_ticket_number"), table_name="fix_rounds")
    op.drop_table("fix_rounds")
    op.drop_index(op.f("ix_fix_halts_ticket_number"), table_name="fix_halts")
    op.drop_table("fix_halts")
    op.drop_index(op.f("ix_evidence_changes_ticket_stage"), table_name="evidence_changes")
    op.drop_table("evidence_changes")
