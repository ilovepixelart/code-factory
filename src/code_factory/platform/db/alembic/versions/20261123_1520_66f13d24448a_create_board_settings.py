"""create board_settings

Revision ID: 66f13d24448a
Revises: 184964d52bbb
Create Date: 2026-11-23 15:20:55.079029

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "66f13d24448a"
down_revision: str | Sequence[str] | None = "184964d52bbb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Two rows at most: the primary key serves every read, so there is no other index.
    op.create_table(
        "board_settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "key IN ('agent_slots', 'prune_days')", name=op.f("ck_board_settings_key")
        ),
        sa.CheckConstraint("value >= 0", name=op.f("ck_board_settings_value")),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_board_settings")),
    )


def downgrade() -> None:
    op.drop_table("board_settings")
