"""Create the follower queue plan: one note per queued ticket.

Revision ID: 60dc9f55a7aa
Revises: dba7d67a8f16
Create Date: 2026-11-24 00:25:48.900884
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "60dc9f55a7aa"
down_revision: str | Sequence[str] | None = "dba7d67a8f16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "follower_queue_plan",
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("planned_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_follower_queue_plan_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_number", name=op.f("pk_follower_queue_plan")),
    )


def downgrade() -> None:
    op.drop_table("follower_queue_plan")
