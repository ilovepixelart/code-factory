"""create undo_entries

Revision ID: 6c1f4a9d2e57
Revises: 3aece4752254
Create Date: 2026-11-23 13:00:00.000000

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6c1f4a9d2e57"
down_revision: str | Sequence[str] | None = "3aece4752254"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # An entry lives 30 seconds, so there is no foreign key and no history to keep.
    op.create_table(
        "undo_entries",
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind <> ''", name=op.f("ck_undo_entries_has_kind")),
        sa.PrimaryKeyConstraint("token", name=op.f("pk_undo_entries")),
    )
    op.create_index("ix_undo_entries_expires_at", "undo_entries", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_undo_entries_expires_at", table_name="undo_entries")
    op.drop_table("undo_entries")
