"""The `column_limits` table: the work-in-progress limit of a board column."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db import Base
from code_factory.ticket_writes.models import STAGES

_STAGE_LIST = ", ".join(f"'{stage}'" for stage in STAGES)


class ColumnLimitRow(Base):
    """A column's limit of open tickets; no row means no limit.

    Global, not per repository. A name that is no board column cannot hold one.
    """

    __tablename__ = "column_limits"
    __table_args__ = (
        CheckConstraint(f"stage IN ({_STAGE_LIST})", name="known_stage"),
        CheckConstraint("max_open > 0", name="max_open_positive"),
    )

    stage: Mapped[str] = mapped_column(Text, primary_key=True)
    max_open: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
