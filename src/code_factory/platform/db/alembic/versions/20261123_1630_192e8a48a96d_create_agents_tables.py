"""create agents tables

Revision ID: 192e8a48a96d
Revises: 64688a1f7cf4
Create Date: 2026-11-23 16:30:04.478324

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "192e8a48a96d"
down_revision: str | Sequence[str] | None = "64688a1f7cf4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Order is behaviour, so `position` is a column; a used connection cannot be dropped (RESTRICT).
    op.create_table(
        "connections",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("key_name", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("management_key_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('anthropic', 'openrouter', 'codex-login', 'lm-studio', 'ollama', "
            "'llama-cpp', 'custom')",
            name=op.f("ck_connections_kind"),
        ),
        sa.CheckConstraint(
            "name ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$'", name=op.f("ck_connections_name")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_connections")),
        sa.UniqueConstraint("name", name=op.f("uq_connections_name")),
    )
    op.create_index("ix_connections_position", "connections", ["position"], unique=False)
    op.create_table(
        "agents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("runtime", sa.Text(), nullable=False),
        sa.Column("connection_id", sa.BigInteger(), nullable=True),
        sa.Column("model", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "roles", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column(
            "types", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column(
            "labels", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("max_tokens", sa.BigInteger(), nullable=True),
        sa.Column("max_seconds", sa.BigInteger(), nullable=True),
        sa.Column("input_price", sa.Double(), nullable=True),
        sa.Column("output_price", sa.Double(), nullable=True),
        sa.Column("max_daily_usd", sa.Double(), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("context_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "input_price >= 0 AND input_price < 'Infinity' "
            "AND output_price >= 0 AND output_price < 'Infinity'",
            name=op.f("ck_agents_prices"),
        ),
        sa.CheckConstraint(
            "max_daily_usd > 0 AND max_daily_usd < 'Infinity'", name=op.f("ck_agents_max_daily_usd")
        ),
        sa.CheckConstraint(
            "name ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$'", name=op.f("ck_agents_name")
        ),
        sa.CheckConstraint(
            "roles <@ ARRAY['spec', 'build', 'review']::text[]", name=op.f("ck_agents_roles")
        ),
        sa.CheckConstraint("runtime IN ('claude', 'codex')", name=op.f("ck_agents_runtime")),
        sa.CheckConstraint(
            "(context IS NULL) = (context_at IS NULL)", name=op.f("ck_agents_context_time")
        ),
        sa.CheckConstraint(
            "(input_price IS NULL) = (output_price IS NULL)", name=op.f("ck_agents_prices_together")
        ),
        sa.CheckConstraint("char_length(context) <= 8000", name=op.f("ck_agents_context_length")),
        sa.CheckConstraint("max_seconds > 0", name=op.f("ck_agents_max_seconds")),
        sa.CheckConstraint("max_tokens > 0", name=op.f("ck_agents_max_tokens")),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["connections.id"],
            name=op.f("fk_agents_connection_id_connections"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agents")),
        sa.UniqueConstraint("name", name=op.f("uq_agents_name")),
    )
    op.create_index("ix_agents_connection_id", "agents", ["connection_id"], unique=False)
    op.create_index("ix_agents_position", "agents", ["position"], unique=False)
    op.create_table(
        "agent_context_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_agent_context_versions_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_context_versions")),
    )
    op.create_index(
        "ix_agent_context_versions_agent_id_at",
        "agent_context_versions",
        ["agent_id", sa.literal_column("at DESC")],
        unique=False,
    )
    op.create_table(
        "agent_model_checks",
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("runtime", sa.Text(), nullable=False),
        sa.Column("connection", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("problem", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=op.f("fk_agent_model_checks_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("agent_id", name=op.f("pk_agent_model_checks")),
    )


def downgrade() -> None:
    op.drop_table("agent_model_checks")
    op.drop_index("ix_agent_context_versions_agent_id_at", table_name="agent_context_versions")
    op.drop_table("agent_context_versions")
    op.drop_index("ix_agents_position", table_name="agents")
    op.drop_index("ix_agents_connection_id", table_name="agents")
    op.drop_table("agents")
    op.drop_index("ix_connections_position", table_name="connections")
    op.drop_table("connections")
