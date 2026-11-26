"""create metrics tables

Revision ID: 5d2f8a1c7e63
Revises: 171d2f76f64e
Create Date: 2026-11-23 17:00:00.000000

Schema only, nothing seeded.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5d2f8a1c7e63"
down_revision: str | Sequence[str] | None = "171d2f76f64e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metrics_merges",
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("commit", sa.Text(), nullable=False),
        sa.Column("head", sa.Text(), nullable=False),
        sa.Column("pull", sa.Integer(), nullable=True),
        sa.Column("branch", sa.Text(), nullable=False),
        sa.Column("ticket_id", sa.Text(), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reverted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("autonomy", sa.Text(), server_default="unknown", nullable=False),
        sa.Column("checks", sa.Text(), server_default="none", nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "autonomy IN ('autonomous', 'assisted', 'unknown')",
            name=op.f("ck_metrics_merges_autonomy"),
        ),
        sa.CheckConstraint(
            "checks IN ('passed', 'failed', 'none')", name=op.f("ck_metrics_merges_checks")
        ),
        sa.PrimaryKeyConstraint("repository", "commit", name=op.f("pk_metrics_merges")),
    )
    op.create_index("ix_metrics_merges_merged_at", "metrics_merges", ["merged_at"], unique=False)
    op.create_table(
        "metrics_branch_cuts",
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("branch", sa.Text(), nullable=False),
        sa.Column("cut_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("repository", "branch", name=op.f("pk_metrics_branch_cuts")),
    )


def downgrade() -> None:
    op.drop_table("metrics_branch_cuts")
    op.drop_index("ix_metrics_merges_merged_at", table_name="metrics_merges")
    op.drop_table("metrics_merges")
