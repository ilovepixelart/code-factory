"""Remove the legacy default zeros whose measurement status cannot be determined."""

from collections.abc import Sequence

from alembic import op

revision: str = "a2efa452d97e"
down_revision: str | Sequence[str] | None = "89d508c0afb2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE eval_records SET cost = NULL WHERE cost = 0 AND receipt IS NULL")
    op.execute("UPDATE eval_judgements SET cost = NULL WHERE cost = 0")


def downgrade() -> None:
    op.execute("UPDATE eval_records SET cost = 0 WHERE cost IS NULL")
    op.execute("UPDATE eval_judgements SET cost = 0 WHERE cost IS NULL")
