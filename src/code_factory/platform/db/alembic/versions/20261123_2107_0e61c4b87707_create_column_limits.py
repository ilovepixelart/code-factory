"""create column limits

Revision ID: 0e61c4b87707
Revises: 5d2f8a1c7e63
Create Date: 2026-11-23 21:07:36.664815

Autogenerate drafted this file; it is read and edited by hand before it is committed.
Schema only, nothing seeded: a column has no limit until the owner sets one.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0e61c4b87707"
down_revision: str | Sequence[str] | None = "5d2f8a1c7e63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "column_limits",
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("max_open", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "stage IN ('spec', 'build', 'review', 'merged')",
            name=op.f("ck_column_limits_known_stage"),
        ),
        sa.CheckConstraint("max_open > 0", name=op.f("ck_column_limits_max_open_positive")),
        sa.PrimaryKeyConstraint("stage", name=op.f("pk_column_limits")),
    )


def downgrade() -> None:
    op.drop_table("column_limits")
