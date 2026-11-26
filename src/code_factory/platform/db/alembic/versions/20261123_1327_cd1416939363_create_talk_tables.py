"""create talk tables

Revision ID: cd1416939363
Revises: 6c1f4a9d2e57
Create Date: 2026-11-23 13:27:27.245441

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "cd1416939363"
down_revision: str | Sequence[str] | None = "6c1f4a9d2e57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "talk_news_marks",
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("post_id", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("answer_id", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_talk_news_marks_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_number", "session_id", name=op.f("pk_talk_news_marks")),
    )
    op.create_table(
        "talk_posts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("route", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_to", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.CheckConstraint(
            "(kind = 'message') = (route <> '')", name=op.f("ck_talk_posts_route_is_for_messages")
        ),
        sa.CheckConstraint(
            "kind = 'comment' OR (path = '' AND line IS NULL)",
            name=op.f("ck_talk_posts_place_is_for_comments"),
        ),
        sa.CheckConstraint("kind IN ('comment', 'message')", name=op.f("ck_talk_posts_known_kind")),
        sa.CheckConstraint(
            "route = '' OR route IN ('run', 'next_run')", name=op.f("ck_talk_posts_known_route")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_talk_posts_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_talk_posts")),
    )
    op.create_index(
        "ix_talk_posts_pending",
        "talk_posts",
        ["ticket_number"],
        unique=False,
        postgresql_where=sa.text("kind = 'message' AND delivered_at IS NULL"),
    )
    op.create_index(
        "ix_talk_posts_ticket_number", "talk_posts", ["ticket_number", "id"], unique=False
    )
    op.create_table(
        "talk_questions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("document", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("several", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "choices",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("asked_by", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_by", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.CheckConstraint(
            "char_length(text) between 1 and 1000", name=op.f("ck_talk_questions_text_length")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_talk_questions_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_talk_questions")),
    )
    op.create_index(
        "ix_talk_questions_ticket_number", "talk_questions", ["ticket_number", "id"], unique=False
    )
    op.create_index(
        "ix_talk_questions_open",
        "talk_questions",
        ["ticket_number", "id"],
        unique=False,
        postgresql_where=sa.text("answered_at IS NULL AND withdrawn_at IS NULL"),
    )
    op.create_index(
        "uq_talk_questions_open_text",
        "talk_questions",
        ["ticket_number", sa.literal_column("md5(text)"), "document"],
        unique=True,
        postgresql_where=sa.text("answered_at IS NULL AND withdrawn_at IS NULL"),
    )
    op.create_table(
        "talk_question_answers",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("question_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "picked", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("by", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "channel IN ('http', 'reply', 'mcp', 'acp', 'cli')",
            name=op.f("ck_talk_question_answers_known_channel"),
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["talk_questions.id"],
            name=op.f("fk_talk_question_answers_question_id_talk_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_talk_question_answers")),
    )
    op.create_index(
        "ix_talk_question_answers_question_id",
        "talk_question_answers",
        ["question_id", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_talk_question_answers_question_id", table_name="talk_question_answers")
    op.drop_table("talk_question_answers")
    op.drop_index(
        "uq_talk_questions_open_text",
        table_name="talk_questions",
        postgresql_where=sa.text("answered_at IS NULL AND withdrawn_at IS NULL"),
    )
    op.drop_index("ix_talk_questions_ticket_number", table_name="talk_questions")
    op.drop_index(
        "ix_talk_questions_open",
        table_name="talk_questions",
        postgresql_where=sa.text("answered_at IS NULL AND withdrawn_at IS NULL"),
    )
    op.drop_table("talk_questions")
    op.drop_index("ix_talk_posts_ticket_number", table_name="talk_posts")
    op.drop_index(
        "ix_talk_posts_pending",
        table_name="talk_posts",
        postgresql_where=sa.text("kind = 'message' AND delivered_at IS NULL"),
    )
    op.drop_table("talk_posts")
    op.drop_table("talk_news_marks")
