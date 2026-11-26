"""create intake_key_grants

Revision ID: 184964d52bbb
Revises: 7c1e5a9d3b42
Create Date: 2026-11-23 13:58:07.257106

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "184964d52bbb"
down_revision: str | Sequence[str] | None = "7c1e5a9d3b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # One row per tracker key: the primary key serves every lookup, so there is no other index.
    op.create_table(
        "intake_key_grants",
        sa.Column("key_name", sa.Text(), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "key_name ~ '^CODE_FACTORY_INTAKE_[A-Z0-9_]+$'",
            name=op.f("ck_intake_key_grants_key_name"),
        ),
        sa.CheckConstraint("url ~ '^https?://'", name=op.f("ck_intake_key_grants_url")),
        sa.PrimaryKeyConstraint("key_name", name=op.f("pk_intake_key_grants")),
    )


def downgrade() -> None:
    op.drop_table("intake_key_grants")
