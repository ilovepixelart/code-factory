"""create schema_info

Revision ID: 2fdc42b35fd5
Revises:
Create Date: 2026-11-23 10:42:26.767289

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2fdc42b35fd5"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schema_info",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("data_format_version", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_schema_info_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schema_info")),
    )


def downgrade() -> None:
    op.drop_table("schema_info")
