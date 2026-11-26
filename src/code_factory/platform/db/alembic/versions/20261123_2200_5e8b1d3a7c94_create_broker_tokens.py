"""create broker tokens

Revision ID: 5e8b1d3a7c94
Revises: 11430b1f7947
Create Date: 2026-11-23 22:00:00.000000

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5e8b1d3a7c94"
down_revision: str | Sequence[str] | None = "5d8e2f4a6c13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broker_tokens",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("digest", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("connection", sa.Text(), nullable=True),
        sa.Column("cap_usd", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("key_state", sa.Text(), server_default=sa.text("'none'"), nullable=False),
        sa.Column("run_key_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("key_state_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delete_claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("key_delete_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("key_delete_error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "cap_usd >= 0 AND cap_usd < 1000000", name=op.f("ck_broker_tokens_cap_in_range")
        ),
        sa.CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name=op.f("ck_broker_tokens_digest_is_sha256_hex")
        ),
        sa.CheckConstraint(
            "key_state IN ('none', 'making', 'made', 'refused')",
            name=op.f("ck_broker_tokens_known_key_state"),
        ),
        sa.CheckConstraint(
            "(key_state = 'made') = (run_key_id IS NOT NULL)",
            name=op.f("ck_broker_tokens_made_key_has_an_id"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_broker_tokens")),
        sa.UniqueConstraint("digest", name=op.f("uq_broker_tokens_digest")),
        sa.UniqueConstraint("run_id", name=op.f("uq_broker_tokens_run_id")),
    )
    op.create_index(
        "ix_broker_tokens_pending",
        "broker_tokens",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("key_state IN ('making', 'made')"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_broker_tokens_pending",
        table_name="broker_tokens",
        postgresql_where=sa.text("key_state IN ('making', 'made')"),
    )
    op.drop_table("broker_tokens")
