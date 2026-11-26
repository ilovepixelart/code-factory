"""The git module's tables. A migration in `alembic/versions` creates them.

`repository` and `ticket_id` carry no foreign key: tracking and tickets belong to other modules,
and a swept ticket leaves an orphan row that `list_trees` reports.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base


class GitTreeRow(Base):
    """The trust record of one board-made place (a clone or a linked worktree).

    A folder under the trees folder with no row is never trusted; removal deletes the row after
    the folder is gone.
    """

    __tablename__ = "git_trees"
    __table_args__ = (
        UniqueConstraint("repository", "name", name="uq_git_trees_repository_name"),
        CheckConstraint("kind IN ('worktree', 'clone')", name="kind"),
        CheckConstraint("token ~ '^[0-9a-f]{32}$'", name="token_form"),
        Index("ix_git_trees_repository_ticket_id", "repository", "ticket_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    repository: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    ticket_id: Mapped[str] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, server_default="0")
    branch: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)
    token: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GitMergeCheckRow(Base):
    """The result of `merge-tree` for two commits, ordered as `pair_key`.

    A merge of two commits is a pure function of them, so a row never goes stale.
    """

    __tablename__ = "git_merge_checks"
    __table_args__ = (
        PrimaryKeyConstraint("repository", "tip_a", "tip_b", name="pk_git_merge_checks"),
        Index("ix_git_merge_checks_checked_at", "checked_at"),
    )

    repository: Mapped[str] = mapped_column(Text)
    tip_a: Mapped[str] = mapped_column(Text)
    tip_b: Mapped[str] = mapped_column(Text)
    clean: Mapped[bool] = mapped_column(Boolean)
    files: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
