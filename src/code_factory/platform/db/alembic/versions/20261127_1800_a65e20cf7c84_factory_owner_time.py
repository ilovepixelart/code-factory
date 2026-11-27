"""Store owner labor inputs per merged pull request in Factory."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a65e20cf7c84"
down_revision: str | Sequence[str] | None = "38df2e9f140d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "factory_owner_time",
        sa.Column("ticket_id", sa.Text(), nullable=False),
        sa.Column("pull_url", sa.Text(), nullable=False),
        sa.Column("active_minutes", sa.BigInteger(), nullable=False),
        sa.Column("hourly_rate_usd", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("ticket_id", "pull_url"),
        sa.CheckConstraint("active_minutes BETWEEN 0 AND 9007199254740991", name="active_minutes"),
        sa.CheckConstraint(
            "hourly_rate_usd BETWEEN 0 AND 9007199254740991", name="hourly_rate_usd"
        ),
    )


def downgrade() -> None:
    op.drop_table("factory_owner_time")
