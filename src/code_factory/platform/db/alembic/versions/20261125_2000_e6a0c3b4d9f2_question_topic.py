"""Give a question a topic: a short label naming what it is about.

A question asked before it has none (`''`). A choice's description and preview live in the
`choices` JSON, so they need no column; a choice written before them reads as having neither.

Revision ID: e6a0c3b4d9f2
Revises: d5f9b2a3c8e1
Create Date: 2026-11-25 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6a0c3b4d9f2"
down_revision: str | Sequence[str] | None = "d5f9b2a3c8e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "talk_questions",
        sa.Column("topic", sa.Text(), server_default=sa.text("''"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("talk_questions", "topic")
