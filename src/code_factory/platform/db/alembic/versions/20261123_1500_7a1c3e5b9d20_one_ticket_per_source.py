"""one ticket per source

Revision ID: 7a1c3e5b9d20
Revises: b58c075fa521
Create Date: 2026-11-23 15:00:00.000000

A source (an issue address, an error fingerprint) names one ticket per repository.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a1c3e5b9d20"
down_revision: str | Sequence[str] | None = "b58c075fa521"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_tickets_repository_source",
        "tickets",
        ["repository", "source"],
        unique=True,
        postgresql_where=sa.text("source <> ''"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_tickets_repository_source",
        table_name="tickets",
        postgresql_where=sa.text("source <> ''"),
    )
