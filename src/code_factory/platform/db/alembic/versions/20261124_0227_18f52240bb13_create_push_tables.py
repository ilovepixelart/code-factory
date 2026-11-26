"""Create the push tables: the target, what was sent, the last failure and the reply tokens.

Revision ID: 18f52240bb13
Revises: 60dc9f55a7aa
Create Date: 2026-11-24 02:27:13.663663
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "18f52240bb13"
down_revision: str | Sequence[str] | None = "60dc9f55a7aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "push_failures",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_push_failures_one_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_failures")),
    )
    op.create_table(
        "push_sent",
        sa.Column("digest", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("digest", name=op.f("pk_push_sent")),
    )
    op.create_table(
        "push_targets",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "format in ('ntfy', 'webhook')", name=op.f("ck_push_targets_format_known")
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_push_targets_one_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_targets")),
    )
    op.create_table(
        "reply_tokens",
        sa.Column("digest", sa.Text(), nullable=False),
        sa.Column("request", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "question",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("minted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(request <> '') <> (jsonb_array_length(question) > 0)",
            name=op.f("ck_reply_tokens_request_or_question"),
        ),
        sa.PrimaryKeyConstraint("digest", name=op.f("pk_reply_tokens")),
    )
    op.create_index(op.f("ix_reply_tokens_request"), "reply_tokens", ["request"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reply_tokens_request"), table_name="reply_tokens")
    op.drop_table("reply_tokens")
    op.drop_table("push_targets")
    op.drop_table("push_sent")
    op.drop_table("push_failures")
