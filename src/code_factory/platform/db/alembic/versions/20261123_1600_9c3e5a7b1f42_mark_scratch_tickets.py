"""mark scratch and trashed tickets, bound mock files

Revision ID: 9c3e5a7b1f42
Revises: 8b2d4f6a0e31
Create Date: 2026-11-23 16:00:00.000000

A scratch ticket exists for one eval run and is deleted after it, history included: the
append-only trigger lets a record go only when its ticket is a scratch ticket.

A mock file row the service would refuse is refused by the table too.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c3e5a7b1f42"
down_revision: str | Sequence[str] | None = "8b2d4f6a0e31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROW_TRIGGER = """
CREATE OR REPLACE FUNCTION ticket_activity_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND EXISTS (
        SELECT 1 FROM tickets WHERE number = OLD.ticket_number AND scratch
    ) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'ticket_activity is append-only: % is refused', TG_OP
        USING ERRCODE = 'restrict_violation';
END
$$
"""

_PLAIN_TRIGGER = """
CREATE OR REPLACE FUNCTION ticket_activity_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'ticket_activity is append-only: % is refused', TG_OP
        USING ERRCODE = 'restrict_violation';
END
$$
"""


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("scratch", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "tickets",
        sa.Column("trashed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.execute(sa.text(_ROW_TRIGGER))
    op.create_check_constraint(
        op.f("ck_ticket_mock_files_has_content"), "ticket_mock_files", "octet_length(data) >= 1"
    )
    op.create_check_constraint(
        op.f("ck_ticket_mock_files_known_content_type"),
        "ticket_mock_files",
        "content_type IN ('image/png', 'image/jpeg', 'image/gif', 'image/webp')",
    )
    op.create_check_constraint(
        op.f("ck_ticket_mock_files_image_name"),
        "ticket_mock_files",
        r"name ~* '\.(png|jpe?g|gif|webp)$'",
    )


def downgrade() -> None:
    for name in ("image_name", "known_content_type", "has_content"):
        op.drop_constraint(op.f(f"ck_ticket_mock_files_{name}"), "ticket_mock_files")
    op.execute(sa.text(_PLAIN_TRIGGER))
    op.drop_column("tickets", "trashed")
    op.drop_column("tickets", "scratch")
