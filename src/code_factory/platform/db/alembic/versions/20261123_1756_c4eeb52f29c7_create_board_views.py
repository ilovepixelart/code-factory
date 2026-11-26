"""create board views

Revision ID: c4eeb52f29c7
Revises: 4a7d2c9e1b53
Create Date: 2026-11-23 17:56:46.031847

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4eeb52f29c7"
down_revision: str | Sequence[str] | None = "4a7d2c9e1b53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "board_views",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.CheckConstraint("name <> ''", name=op.f("ck_board_views_has_name")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_board_views")),
        sa.UniqueConstraint("name", name=op.f("uq_board_views_name")),
    )


def downgrade() -> None:
    op.drop_table("board_views")
