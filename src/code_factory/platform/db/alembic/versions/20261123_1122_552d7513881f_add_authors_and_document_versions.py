"""add authors and document versions

Revision ID: 552d7513881f
Revises: 47b50762fe9e
Create Date: 2026-11-23 11:22:17.674968

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "552d7513881f"
down_revision: str | Sequence[str] | None = "47b50762fe9e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Constant defaults: Postgres adds these without rewriting the table, and ADD COLUMN fires no
    # row trigger, so the append-only trigger on ticket_activity does not refuse it.
    op.add_column(
        "ticket_activity", sa.Column("by", sa.Text(), server_default=sa.text("''"), nullable=False)
    )
    op.create_index("ix_ticket_activity_by", "ticket_activity", ["by", "kind"], unique=False)
    op.add_column(
        "ticket_documents",
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "ticket_documents",
        sa.Column("updated_by", sa.Text(), server_default=sa.text("''"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("ticket_documents", "updated_by")
    op.drop_column("ticket_documents", "version")
    op.drop_index("ix_ticket_activity_by", table_name="ticket_activity")
    op.drop_column("ticket_activity", "by")
