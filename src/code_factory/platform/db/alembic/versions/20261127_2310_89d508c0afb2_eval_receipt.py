"""Identify evaluation receipts and permit unknown measurement costs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "89d508c0afb2"
down_revision: str | Sequence[str] | None = "cca36d85d75a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("eval_records", sa.Column("receipt", sa.Text(), nullable=True))
    op.create_index(
        "uq_eval_records_receipt",
        "eval_records",
        ["repository", "receipt"],
        unique=True,
        postgresql_where=sa.text("receipt IS NOT NULL"),
    )
    for table, axis in (("eval_records", "recorded_at"), ("eval_judgements", "at")):
        op.alter_column(
            table, "cost", existing_type=sa.Double(), server_default=None, nullable=True
        )
        op.create_index(
            f"ix_{table}_measurement",
            table,
            [axis],
            postgresql_where=sa.text("cost IS NOT NULL"),
        )


def downgrade() -> None:
    for table in ("eval_records", "eval_judgements"):
        op.drop_index(f"ix_{table}_measurement", table_name=table)
        op.alter_column(
            table, "cost", existing_type=sa.Double(), server_default=sa.text("0"), nullable=False
        )
    op.drop_index("uq_eval_records_receipt", table_name="eval_records")
    op.drop_column("eval_records", "receipt")
