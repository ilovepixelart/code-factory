"""Keep delivery facts per pull request independently of the ticket's active pull."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3b368180bf21"
down_revision: str | Sequence[str] | None = "a65e20cf7c84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delivery_pull_history",
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("merged_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("first_review_at", sa.DateTime(timezone=True)),
        sa.Column("changed_lines", sa.Integer()),
        sa.ForeignKeyConstraint(["ticket_number"], ["tickets.number"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("url"),
        sa.CheckConstraint("state IN ('', 'open', 'merged', 'closed')", name="known_state"),
    )
    op.create_index("ix_delivery_pull_history_ticket", "delivery_pull_history", ["ticket_number"])
    op.create_index("ix_delivery_pull_history_opened", "delivery_pull_history", ["opened_at"])
    op.create_index(
        "ix_delivery_pull_history_merged",
        "delivery_pull_history",
        ["merged_at"],
        postgresql_where=sa.text("merged_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("delivery_pull_history")
