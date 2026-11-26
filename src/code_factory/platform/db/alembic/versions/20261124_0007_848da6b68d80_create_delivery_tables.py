"""Create the delivery tables: pulls, events, intake, polls and issue status.

Revision ID: 848da6b68d80
Revises: 5e8b1d3a7c94
Create Date: 2026-11-24 00:07:28.405886
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "848da6b68d80"
down_revision: str | Sequence[str] | None = "5e8b1d3a7c94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delivery_intake",
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("tracker", sa.Text(), nullable=False),
        sa.Column("ticket_id", sa.Text(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tracker IN ('github', 'linear', 'jira', 'slack')",
            name=op.f("ck_delivery_intake_known_tracker"),
        ),
        sa.PrimaryKeyConstraint("repository", "source", name=op.f("pk_delivery_intake")),
    )
    op.create_index("ix_delivery_intake_ticket", "delivery_intake", ["ticket_id"], unique=False)
    op.create_table(
        "delivery_polls",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("listed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_delivery_polls")),
    )
    op.create_table(
        "delivery_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("head", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("reason", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("by", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("from_base", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("to_base", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            (
                "kind IN ('ship_started', 'ship_pushed', 'ship_failed', 'pull_request', "
                "'branch_pushed', 'merged_pull_request', 'merge_failed', 'merge_base_unread', "
                "'retargeted_pull_request')"
            ),
            name=op.f("ck_delivery_events_known_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_delivery_events_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delivery_events")),
    )
    op.create_index(
        "ix_delivery_events_once_per_head",
        "delivery_events",
        ["ticket_number", "url", "head"],
        unique=True,
        postgresql_where=sa.text("kind IN ('pull_request', 'branch_pushed', 'merge_base_unread')"),
    )
    op.create_index(
        "ix_delivery_events_once_per_url",
        "delivery_events",
        ["ticket_number", "url"],
        unique=True,
        postgresql_where=sa.text("kind IN ('merged_pull_request', 'retargeted_pull_request')"),
    )
    op.create_index(
        "ix_delivery_events_ticket",
        "delivery_events",
        ["ticket_number", sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_table(
        "delivery_issue_status",
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("tracker", sa.Text(), nullable=False),
        sa.Column("issue", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("comment", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("body", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("opened_told", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("merged_told", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tracker IN ('github', 'linear', 'jira', 'slack')",
            name=op.f("ck_delivery_issue_status_known_tracker"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_delivery_issue_status_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_number", name=op.f("pk_delivery_issue_status")),
    )
    op.create_table(
        "delivery_pulls",
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("state", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("review", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("ci", sa.Text(), server_default=sa.text("'none'"), nullable=False),
        sa.Column("other_ci", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("head", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("base", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("draft", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("conflict", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("own_pending", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("reviewed", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("merge_state", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("shipped_head", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("since", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ci IN ('none', 'passed', 'failed', 'pending')", name=op.f("ck_delivery_pulls_known_ci")
        ),
        sa.CheckConstraint(
            "state IN ('', 'open', 'merged', 'closed')", name=op.f("ck_delivery_pulls_known_state")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_delivery_pulls_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_number", name=op.f("pk_delivery_pulls")),
    )
    op.create_index(
        "ix_delivery_pulls_open",
        "delivery_pulls",
        ["repository"],
        unique=False,
        postgresql_where=sa.text("state = 'open'"),
    )
    op.create_index(
        "ix_delivery_pulls_url",
        "delivery_pulls",
        ["url"],
        unique=True,
        postgresql_where=sa.text("url <> ''"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_delivery_pulls_url", table_name="delivery_pulls", postgresql_where=sa.text("url <> ''")
    )
    op.drop_index(
        "ix_delivery_pulls_open",
        table_name="delivery_pulls",
        postgresql_where=sa.text("state = 'open'"),
    )
    op.drop_table("delivery_pulls")
    op.drop_table("delivery_issue_status")
    op.drop_index("ix_delivery_events_ticket", table_name="delivery_events")
    op.drop_index(
        "ix_delivery_events_once_per_url",
        table_name="delivery_events",
        postgresql_where=sa.text("kind IN ('merged_pull_request', 'retargeted_pull_request')"),
    )
    op.drop_index(
        "ix_delivery_events_once_per_head",
        table_name="delivery_events",
        postgresql_where=sa.text("kind IN ('pull_request', 'branch_pushed', 'merge_base_unread')"),
    )
    op.drop_table("delivery_events")
    op.drop_table("delivery_polls")
    op.drop_index("ix_delivery_intake_ticket", table_name="delivery_intake")
    op.drop_table("delivery_intake")
