"""Store GitHub timestamps for pull request attention and activity."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "38df2e9f140d"
down_revision: str | Sequence[str] | None = "e6a0c3b4d9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("created_on_host", "updated_on_host", "merged_on_host", "first_review_at")


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column("delivery_pulls", sa.Column(name, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("delivery_pulls", name)
