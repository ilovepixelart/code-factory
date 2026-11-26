"""create memory deliveries

Revision ID: 46c9b8926d6f
Revises: 192e8a48a96d
Create Date: 2026-11-23 17:20:25.781030

Schema only, nothing seeded.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "46c9b8926d6f"
down_revision: str | Sequence[str] | None = "192e8a48a96d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_deliveries",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("entry_id", sa.Text(), nullable=False),
        sa.Column("ticket_id", sa.Text(), nullable=False),
        sa.Column("left_out", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["repository", "entry_id"],
            ["memory_entries.repository", "memory_entries.name"],
            name=op.f("fk_memory_deliveries_repository_memory_entries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "run_id", "repository", "entry_id", name=op.f("pk_memory_deliveries")
        ),
    )
    op.create_index(
        "ix_memory_deliveries_entry",
        "memory_deliveries",
        ["repository", "entry_id", sa.literal_column("delivered_at DESC")],
        unique=False,
    )
    op.create_index("ix_memory_deliveries_run_id", "memory_deliveries", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_memory_deliveries_run_id", table_name="memory_deliveries")
    op.drop_index("ix_memory_deliveries_entry", table_name="memory_deliveries")
    op.drop_table("memory_deliveries")
