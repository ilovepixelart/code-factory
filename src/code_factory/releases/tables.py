"""The releases module's tables. A migration in `alembic/versions` creates them.

A release has three states, derived from its columns and never stored: a draft (editable, names
no ticket), published (`published_at` set: the notes are final and `release_tickets` lists the
tickets they name) and tagged (`tagged_at` set: the tag reached origin). `published_at`,
`tag_commit` and `tagged_at` are the only nullable columns: absence is the state.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base


class ReleaseRow(Base):
    """One version of a tracked repository.

    `repository` has no foreign key: tracking belongs to another module, and untracking must keep
    the history of what shipped.
    """

    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("repository", "version", name="uq_releases_repository_version"),
        CheckConstraint("version ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$'", name="version"),
        CheckConstraint("tag_commit ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'", name="tag_commit_form"),
        CheckConstraint("tag_commit IS NULL OR published_at IS NOT NULL", name="tag_after_publish"),
        CheckConstraint("tagged_at IS NULL OR tag_commit IS NOT NULL", name="tagged_has_commit"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    repository: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text)
    drafted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Written before the tag is pushed, so a crash between the push and `tagged_at` resumes.
    tag_commit: Mapped[str | None] = mapped_column(Text)
    tagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReleaseTicketRow(Base):
    """A ticket id a published release names, derived once at publish from its notes.

    `ticket_id` (`CF-12`) has no foreign key: a purged ticket must not block a release. The index
    on it serves `naming`, which asks for up to thousands of tickets in one statement.
    """

    __tablename__ = "release_tickets"
    __table_args__ = (Index("ix_release_tickets_ticket_id", "ticket_id"),)

    release_id: Mapped[int] = mapped_column(
        ForeignKey("releases.id", ondelete="CASCADE"), primary_key=True
    )
    ticket_id: Mapped[str] = mapped_column(Text, primary_key=True)
