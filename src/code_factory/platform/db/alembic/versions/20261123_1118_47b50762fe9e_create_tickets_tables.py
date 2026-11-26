"""create tickets tables

Revision ID: 47b50762fe9e
Revises: b8d6a63526ff
Create Date: 2026-11-23 11:18:19.108452

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "47b50762fe9e"
down_revision: str | Sequence[str] | None = "b8d6a63526ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("number", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), server_default=sa.text("'feature'"), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("labels", sa.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("priority", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("assignee", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("due", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("blocked", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("rank", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("e2e", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("tests", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("budget", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("parallel", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("source", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("steps", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("pages", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("branch", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("merged", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
            "priority IN ('', 'urgent', 'high', 'medium', 'low')",
            name=op.f("ck_tickets_known_priority"),
        ),
        sa.CheckConstraint("title <> ''", name=op.f("ck_tickets_has_title")),
        sa.CheckConstraint(
            "type IN ('feature', 'bug', 'refactor', 'upgrade', 'hotfix', 'docs')",
            name=op.f("ck_tickets_known_type"),
        ),
        sa.CheckConstraint("rank >= 0", name=op.f("ck_tickets_rank_not_negative")),
        sa.PrimaryKeyConstraint("number", name=op.f("pk_tickets")),
    )
    op.create_index(op.f("ix_tickets_repository"), "tickets", ["repository"], unique=False)
    op.create_table(
        "ticket_activity",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_ticket_activity_ticket_number_tickets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_activity")),
    )
    op.create_index(
        "ix_ticket_activity_ticket_number", "ticket_activity", ["ticket_number", "id"], unique=False
    )
    # History is append-only: the database itself refuses to change or remove a record.
    op.execute(
        sa.text(
            """
            CREATE FUNCTION ticket_activity_append_only() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'ticket_activity is append-only: % is refused', TG_OP
                    USING ERRCODE = 'restrict_violation';
            END
            $$
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER ticket_activity_append_only BEFORE UPDATE OR DELETE ON ticket_activity "
            "FOR EACH ROW EXECUTE FUNCTION ticket_activity_append_only()"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER ticket_activity_no_truncate BEFORE TRUNCATE ON ticket_activity "
            "FOR EACH STATEMENT EXECUTE FUNCTION ticket_activity_append_only()"
        )
    )
    op.create_table(
        "ticket_documents",
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_ticket_documents_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_number", "name", name=op.f("pk_ticket_documents")),
    )
    op.create_table(
        "ticket_links",
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("linked_number", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('parent', 'blocked_by', 'caused_by')", name=op.f("ck_ticket_links_known_kind")
        ),
        sa.CheckConstraint(
            "ticket_number <> linked_number", name=op.f("ck_ticket_links_not_itself")
        ),
        sa.ForeignKeyConstraint(
            ["linked_number"],
            ["tickets.number"],
            name=op.f("fk_ticket_links_linked_number_tickets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_ticket_links_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "ticket_number", "kind", "linked_number", name=op.f("pk_ticket_links")
        ),
    )
    op.create_index(
        op.f("ix_ticket_links_linked_number"), "ticket_links", ["linked_number"], unique=False
    )
    op.create_index(
        "uq_ticket_links_one_parent",
        "ticket_links",
        ["ticket_number"],
        unique=True,
        postgresql_where=sa.text("kind = 'parent'"),
    )
    op.create_table(
        "ticket_pull_requests",
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('open', 'closed', 'merged')",
            name=op.f("ck_ticket_pull_requests_known_state"),
        ),
        sa.CheckConstraint("number > 0", name=op.f("ck_ticket_pull_requests_positive_number")),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_ticket_pull_requests_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_number", name=op.f("pk_ticket_pull_requests")),
    )


def downgrade() -> None:
    op.drop_table("ticket_pull_requests")
    op.drop_index(
        "uq_ticket_links_one_parent",
        table_name="ticket_links",
        postgresql_where=sa.text("kind = 'parent'"),
    )
    op.drop_index(op.f("ix_ticket_links_linked_number"), table_name="ticket_links")
    op.drop_table("ticket_links")
    op.drop_table("ticket_documents")
    op.drop_index("ix_ticket_activity_ticket_number", table_name="ticket_activity")
    op.execute(sa.text("DROP TRIGGER ticket_activity_no_truncate ON ticket_activity"))
    op.execute(sa.text("DROP TRIGGER ticket_activity_append_only ON ticket_activity"))
    op.execute(sa.text("DROP FUNCTION ticket_activity_append_only()"))
    op.drop_table("ticket_activity")
    op.drop_index(op.f("ix_tickets_repository"), table_name="tickets")
    op.drop_table("tickets")
