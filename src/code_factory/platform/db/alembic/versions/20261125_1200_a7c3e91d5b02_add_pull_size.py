"""Add a pull request's size: the lines it adds and deletes and the files it changes.

Nullable: a pull request read before this revision, or one GitHub gave no count for, has no size
until its next read, and the board shows none rather than a zero.

Revision ID: a7c3e91d5b02
Revises: 18f52240bb13
Create Date: 2026-11-25 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e91d5b02"
down_revision: str | Sequence[str] | None = "18f52240bb13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("delivery_pulls", sa.Column("additions", sa.Integer(), nullable=True))
    op.add_column("delivery_pulls", sa.Column("deletions", sa.Integer(), nullable=True))
    op.add_column("delivery_pulls", sa.Column("changed_files", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("delivery_pulls", "changed_files")
    op.drop_column("delivery_pulls", "deletions")
    op.drop_column("delivery_pulls", "additions")
