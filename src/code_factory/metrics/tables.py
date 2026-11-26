"""The metrics module's tables. A migration in `alembic/versions` creates them.

They hold git facts that outlive tickets and name tickets (old branches) that may not exist, so
neither has a foreign key. `repository` is the tracked repository's name as tickets key it.
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base


class MergeRow(Base):
    """One pull request merged into a default branch (a merge on its first-parent line)."""

    __tablename__ = "metrics_merges"
    __table_args__ = (
        CheckConstraint("autonomy IN ('autonomous', 'assisted', 'unknown')", name="autonomy"),
        CheckConstraint("checks IN ('passed', 'failed', 'none')", name="checks"),
        Index("ix_metrics_merges_merged_at", "merged_at"),
    )

    repository: Mapped[str] = mapped_column(Text, primary_key=True)
    commit: Mapped[str] = mapped_column(Text, primary_key=True)
    head: Mapped[str] = mapped_column(Text)
    pull: Mapped[int | None] = mapped_column(Integer)
    branch: Mapped[str] = mapped_column(Text)
    ticket_id: Mapped[str | None] = mapped_column(Text)
    merged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reverted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    autonomy: Mapped[str] = mapped_column(Text, server_default="unknown")
    checks: Mapped[str] = mapped_column(Text, server_default="none")
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BranchCutRow(Base):
    """When a branch in flight was cut; `cut_at` is NULL while git cannot tell."""

    __tablename__ = "metrics_branch_cuts"

    repository: Mapped[str] = mapped_column(Text, primary_key=True)
    branch: Mapped[str] = mapped_column(Text, primary_key=True)
    cut_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
