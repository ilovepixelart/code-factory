"""record who proposed a memory entry

Revision ID: 2b98cdc72258
Revises: 0e0ddda17a69
Create Date: 2026-11-23 11:51:25.390643

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2b98cdc72258"
down_revision: str | Sequence[str] | None = "0e0ddda17a69"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_entries",
        sa.Column("proposed_by", sa.Text(), server_default=sa.text("''"), nullable=False),
    )
    op.drop_index(op.f("ix_memory_entries_created_by"), table_name="memory_entries")
    op.create_index(
        "ix_memory_entries_proposed_by", "memory_entries", ["proposed_by"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_memory_entries_proposed_by", table_name="memory_entries")
    op.create_index(
        op.f("ix_memory_entries_created_by"), "memory_entries", ["created_by"], unique=False
    )
    op.drop_column("memory_entries", "proposed_by")
