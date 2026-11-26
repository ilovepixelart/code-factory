"""The delivery module's tables. A ticket is addressed by `ticket_number` (the tickets key).

Every row but intake goes with its ticket (`CASCADE`); intake outlives it, so a deleted ticket's
issue is never imported again. Times are `timestamptz`; every field is a column.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base

_EMPTY = text("''")
_FALSE = text("false")
_FK = "tickets.number"
KINDS = (
    "ship_started",
    "ship_pushed",
    "ship_failed",
    "pull_request",
    "branch_pushed",
    "merged_pull_request",
    "merge_failed",
    "merge_base_unread",
    "retargeted_pull_request",
)
TRACKERS = ("github", "linear", "jira", "slack")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class PullRow(Base):
    """A ticket's pull request as last read, and the commit the board shipped to it."""

    __tablename__ = "delivery_pulls"
    __table_args__ = (
        CheckConstraint("state IN ('', 'open', 'merged', 'closed')", name="known_state"),
        CheckConstraint("ci IN ('none', 'passed', 'failed', 'pending')", name="known_ci"),
        Index("ix_delivery_pulls_url", "url", unique=True, postgresql_where=text("url <> ''")),
        Index("ix_delivery_pulls_open", "repository", postgresql_where=text("state = 'open'")),
    )

    ticket_number: Mapped[int] = mapped_column(
        ForeignKey(_FK, ondelete="CASCADE"), primary_key=True
    )
    repository: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    state: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    review: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    ci: Mapped[str] = mapped_column(Text, server_default=text("'none'"))
    other_ci: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    head: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    base: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    draft: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    conflict: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    own_pending: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    reviewed: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    merge_state: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    additions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deletions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    changed_files: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_on_host: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_on_host: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merged_on_host: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_head: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventRow(Base):
    """What delivery did, append only; the partial unique indexes make each record once-only."""

    __tablename__ = "delivery_events"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_quoted(KINDS)})", name="known_kind"),
        Index("ix_delivery_events_ticket", "ticket_number", text("id DESC")),
        Index(
            "ix_delivery_events_once_per_head",
            "ticket_number",
            "url",
            "head",
            unique=True,
            postgresql_where=text("kind IN ('pull_request', 'branch_pushed', 'merge_base_unread')"),
        ),
        Index(
            "ix_delivery_events_once_per_url",
            "ticket_number",
            "url",
            unique=True,
            postgresql_where=text("kind IN ('merged_pull_request', 'retargeted_pull_request')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ticket_number: Mapped[int] = mapped_column(ForeignKey(_FK, ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    head: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    reason: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    by: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    from_base: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    to_base: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    # Null means final; a time means the effect is tried again then.
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IntakeRow(Base):
    """An issue imported as a ticket, once for ever; no foreign key on purpose."""

    __tablename__ = "delivery_intake"
    __table_args__ = (
        CheckConstraint(f"tracker IN ({_quoted(TRACKERS)})", name="known_tracker"),
        Index("ix_delivery_intake_ticket", "ticket_id"),
    )

    repository: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text, primary_key=True)
    tracker: Mapped[str] = mapped_column(Text)
    ticket_id: Mapped[str] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PollRow(Base):
    """When a listing was last claimed; one claim a minute per key."""

    __tablename__ = "delivery_polls"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    listed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IssueStatusRow(Base):
    """The one status comment on an imported issue, and what it last said."""

    __tablename__ = "delivery_issue_status"
    __table_args__ = (CheckConstraint(f"tracker IN ({_quoted(TRACKERS)})", name="known_tracker"),)

    ticket_number: Mapped[int] = mapped_column(
        ForeignKey(_FK, ondelete="CASCADE"), primary_key=True
    )
    tracker: Mapped[str] = mapped_column(Text)
    issue: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    comment: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    body: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    opened_told: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    merged_told: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
