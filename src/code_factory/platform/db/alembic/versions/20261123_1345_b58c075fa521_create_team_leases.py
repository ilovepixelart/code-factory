"""create team leases

Revision ID: b58c075fa521
Revises: 66f13d24448a
Create Date: 2026-11-23 13:45:46.588311

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b58c075fa521"
down_revision: str | Sequence[str] | None = "66f13d24448a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Claims are transient (a claim is free 60 s after its last beat), so nothing is imported.
    op.create_table(
        "team_leases",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("ticket_number", sa.BigInteger(), nullable=False),
        sa.Column("agent", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_number"],
            ["tickets.number"],
            name=op.f("fk_team_leases_ticket_number_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_leases")),
        sa.UniqueConstraint("ticket_number", name=op.f("uq_team_leases_ticket_number")),
    )
    op.create_index(op.f("ix_team_leases_agent"), "team_leases", ["agent"], unique=False)
    # No foreign key to the runs table: another module owns it, and a claim may name a run that
    # is not recorded.
    op.create_table(
        "team_lease_runs",
        sa.Column("lease_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["lease_id"],
            ["team_leases.id"],
            name=op.f("fk_team_lease_runs_lease_id_team_leases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("lease_id", "run_id", name=op.f("pk_team_lease_runs")),
    )
    op.create_index(op.f("ix_team_lease_runs_run_id"), "team_lease_runs", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_team_lease_runs_run_id"), table_name="team_lease_runs")
    op.drop_table("team_lease_runs")
    op.drop_index(op.f("ix_team_leases_agent"), table_name="team_leases")
    op.drop_table("team_leases")
