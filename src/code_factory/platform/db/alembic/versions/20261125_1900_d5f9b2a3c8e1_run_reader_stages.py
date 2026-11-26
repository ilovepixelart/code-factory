"""Let a run read a ticket's spec or critique its plan: the read and critique stages.

Revision ID: d5f9b2a3c8e1
Revises: c4e8a1f2b7d9
Create Date: 2026-11-25 19:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d5f9b2a3c8e1"
down_revision: str | Sequence[str] | None = "c4e8a1f2b7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = "stage IN ('spec', 'build', 'review', 'split', 'coordinate', 'qa', 'security', 'tests')"
_AFTER = (
    "stage IN ('spec', 'build', 'review', 'split', 'coordinate', 'qa', 'security', 'tests', "
    "'read', 'critique')"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_runs_known_stage"), "runs", type_="check")
    op.create_check_constraint(op.f("ck_runs_known_stage"), "runs", _AFTER)


def downgrade() -> None:
    op.drop_constraint(op.f("ck_runs_known_stage"), "runs", type_="check")
    op.create_check_constraint(op.f("ck_runs_known_stage"), "runs", _BEFORE)
