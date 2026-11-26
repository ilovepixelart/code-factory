"""create releases tables

Revision ID: 7c1e5a9d3b42
Revises: cd1416939363
Create Date: 2026-11-23 13:30:00.000000

Schema only, nothing seeded.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c1e5a9d3b42"
down_revision: str | Sequence[str] | None = "cd1416939363"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "releases",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column(
            "drafted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tag_commit", sa.Text(), nullable=True),
        sa.Column("tagged_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name=op.f("ck_releases_version")
        ),
        sa.CheckConstraint(
            "tag_commit ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'", name=op.f("ck_releases_tag_commit_form")
        ),
        sa.CheckConstraint(
            "tag_commit IS NULL OR published_at IS NOT NULL",
            name=op.f("ck_releases_tag_after_publish"),
        ),
        sa.CheckConstraint(
            "tagged_at IS NULL OR tag_commit IS NOT NULL",
            name=op.f("ck_releases_tagged_has_commit"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_releases")),
        sa.UniqueConstraint("repository", "version", name=op.f("uq_releases_repository_version")),
    )
    op.create_table(
        "release_tickets",
        sa.Column("release_id", sa.BigInteger(), nullable=False),
        sa.Column("ticket_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["releases.id"],
            name=op.f("fk_release_tickets_release_id_releases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("release_id", "ticket_id", name=op.f("pk_release_tickets")),
    )
    op.create_index("ix_release_tickets_ticket_id", "release_tickets", ["ticket_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_release_tickets_ticket_id", table_name="release_tickets")
    op.drop_table("release_tickets")
    op.drop_table("releases")
