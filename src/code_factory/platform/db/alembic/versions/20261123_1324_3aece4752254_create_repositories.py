"""create repositories

Revision ID: 3aece4752254
Revises: 2b98cdc72258
Create Date: 2026-11-23 13:24:11.376171

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3aece4752254"
down_revision: str | Sequence[str] | None = "2b98cdc72258"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("name <> ''", name=op.f("ck_repositories_has_name")),
        sa.CheckConstraint("path LIKE '/%'", name=op.f("ck_repositories_absolute_path")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repositories")),
        sa.UniqueConstraint("name", name=op.f("uq_repositories_name")),
    )


def downgrade() -> None:
    op.drop_table("repositories")
