"""Let a run be a review role: qa, security or tests, beside the stages it was.

Revision ID: c4e8a1f2b7d9
Revises: a7c3e91d5b02
Create Date: 2026-11-25 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4e8a1f2b7d9"
down_revision: str | Sequence[str] | None = "a7c3e91d5b02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = "stage IN ('spec', 'build', 'review', 'split', 'coordinate')"
_AFTER = "stage IN ('spec', 'build', 'review', 'split', 'coordinate', 'qa', 'security', 'tests')"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_runs_known_stage"), "runs", type_="check")
    op.create_check_constraint(op.f("ck_runs_known_stage"), "runs", _AFTER)


def downgrade() -> None:
    op.drop_constraint(op.f("ck_runs_known_stage"), "runs", type_="check")
    op.create_check_constraint(op.f("ck_runs_known_stage"), "runs", _BEFORE)
