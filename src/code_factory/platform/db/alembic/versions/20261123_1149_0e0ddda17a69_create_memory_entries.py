"""create memory entries

Revision ID: 0e0ddda17a69
Revises: 0d92425c8a52
Create Date: 2026-11-23 11:49:39.895460

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0e0ddda17a69"
down_revision: str | Sequence[str] | None = "0d92425c8a52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("why", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("source", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("guard", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("scope", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "supersedes",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("expires", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("until_ticket", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "cites", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("proposed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("verdict", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("written_on", sa.Date(), nullable=False),
        sa.Column("reviewed", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("retired", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("merged_into", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("created_by", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('rule', 'decision', 'lesson')", name=op.f("ck_memory_entries_known_kind")
        ),
        sa.CheckConstraint("statement <> ''", name=op.f("ck_memory_entries_has_statement")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_entries")),
        sa.UniqueConstraint("repository", "name", name=op.f("uq_memory_entries_repository")),
    )
    op.create_index("ix_memory_entries_created_by", "memory_entries", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_memory_entries_created_by", table_name="memory_entries")
    op.drop_table("memory_entries")
