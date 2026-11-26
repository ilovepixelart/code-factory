"""create git tables

Revision ID: 4a7d2c9e1b53
Revises: 9c3e5a7b1f42
Create Date: 2026-11-23 14:00:00.000000

Schema only, nothing seeded.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4a7d2c9e1b53"
down_revision: str | Sequence[str] | None = "9c3e5a7b1f42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "git_trees",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ticket_id", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("branch", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('worktree', 'clone')", name=op.f("ck_git_trees_kind")),
        sa.CheckConstraint("token ~ '^[0-9a-f]{32}$'", name=op.f("ck_git_trees_token_form")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_git_trees")),
        sa.UniqueConstraint("repository", "name", name=op.f("uq_git_trees_repository_name")),
    )
    op.create_index(
        "ix_git_trees_repository_ticket_id", "git_trees", ["repository", "ticket_id"], unique=False
    )
    op.create_table(
        "git_merge_checks",
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("tip_a", sa.Text(), nullable=False),
        sa.Column("tip_b", sa.Text(), nullable=False),
        sa.Column("clean", sa.Boolean(), nullable=False),
        sa.Column("files", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("repository", "tip_a", "tip_b", name="pk_git_merge_checks"),
    )
    op.create_index(
        "ix_git_merge_checks_checked_at", "git_merge_checks", ["checked_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_git_merge_checks_checked_at", table_name="git_merge_checks")
    op.drop_table("git_merge_checks")
    op.drop_index("ix_git_trees_repository_ticket_id", table_name="git_trees")
    op.drop_table("git_trees")
