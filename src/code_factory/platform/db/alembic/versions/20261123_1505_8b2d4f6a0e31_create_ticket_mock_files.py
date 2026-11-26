"""create ticket mock files

Revision ID: 8b2d4f6a0e31
Revises: 7a1c3e5b9d20
Create Date: 2026-11-23 15:05:00.000000

A ticket's mock images are rows of the ticket, served by the page.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8b2d4f6a0e31"
down_revision: str | Sequence[str] | None = "7a1c3e5b9d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ticket_mock_files",
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("updated_by", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("name <> ''", name=op.f("ck_ticket_mock_files_has_name")),
        sa.CheckConstraint(
            "octet_length(data) <= 16777216", name=op.f("ck_ticket_mock_files_within_size_limit")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_ticket_mock_files_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_number", "name", name=op.f("pk_ticket_mock_files")),
    )


def downgrade() -> None:
    op.drop_table("ticket_mock_files")
