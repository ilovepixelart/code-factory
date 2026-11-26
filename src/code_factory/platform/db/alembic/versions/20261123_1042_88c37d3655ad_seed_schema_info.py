"""seed schema_info

Revision ID: 88c37d3655ad
Revises: 2fdc42b35fd5
Create Date: 2026-11-23 10:42:32.574032

Autogenerate drafted this file; it is read and edited by hand before it is committed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "88c37d3655ad"
down_revision: str | Sequence[str] | None = "2fdc42b35fd5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Data migration, kept apart from the schema revision above. The literal 1 is the data format
    # this revision writes; it is deliberately not imported from the application, which moves on.
    op.execute(sa.text("INSERT INTO schema_info (id, data_format_version) VALUES (1, 1)"))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM schema_info WHERE id = 1"))
