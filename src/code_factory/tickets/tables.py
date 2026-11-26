"""The tickets module's tables. A migration in `alembic/versions` creates each one.

Every column is NOT NULL: an optional text field is `''` when unset (as the app reads it), and an
optional relation is a row of its own (`ticket_links`, `ticket_pull_requests`) that exists only
while the fact holds. The column a ticket is in is never stored: `rules.column_of` reads it from
`branch`, the pull request row and `merged`.
"""

from datetime import datetime
from typing import Any, get_args

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Text,
    and_,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base
from code_factory.tickets.models import Priority, PullRequestState, TicketType

_FK = "tickets.number"

_EMPTY = text("''")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


TYPES = get_args(TicketType)
PRIORITIES = get_args(Priority)
LINK_KINDS = ("parent", "blocked_by", "caused_by")
PULL_REQUEST_STATES = tuple(state.value for state in PullRequestState)
MOCK_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")


class TicketRow(Base):
    """One ticket. `number` is its identity, `CF-<number>`, always drawn from the sequence."""

    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(f"type IN ({_quoted(TYPES)})", name="known_type"),
        CheckConstraint(f"priority IN ({_quoted(PRIORITIES)})", name="known_priority"),
        CheckConstraint("rank >= 0", name="rank_not_negative"),
        CheckConstraint("title <> ''", name="has_title"),
        # A source (an issue, an error fingerprint) is filed once per repository.
        Index(
            "uq_tickets_repository_source",
            "repository",
            "source",
            unique=True,
            postgresql_where=text("source <> ''"),
        ),
    )

    number: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    repository: Mapped[str] = mapped_column(Text, index=True)
    title: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text, server_default=text("'feature'"))
    description: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    labels: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    priority: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    assignee: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    due: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    blocked: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    rank: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    e2e: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    tests: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    budget: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    parallel: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    source: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    steps: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    pages: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    archived: Mapped[bool] = mapped_column(server_default=text("false"))
    # Filed for one eval run: on no board, list or count, and deleted with its history after it.
    scratch: Mapped[bool] = mapped_column(server_default=text("false"))
    # Deleted from the board: every read hides it and the row stays, as its history does.
    trashed: Mapped[bool] = mapped_column(server_default=text("false"))
    branch: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    merged: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# What a list, count or flow read counts: a scratch or trashed ticket is on no board.
VISIBLE = and_(TicketRow.scratch.is_(False), TicketRow.trashed.is_(False))


class TicketLinkRow(Base):
    """A link from a ticket to another: its parent, a blocker, or a ticket it is a defect of.

    A linked ticket cannot be deleted while linked (`RESTRICT`); the links go with the ticket that
    holds them (`CASCADE`). A ticket has at most one parent (`uq_ticket_links_one_parent`).
    """

    __tablename__ = "ticket_links"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_quoted(LINK_KINDS)})", name="known_kind"),
        CheckConstraint("ticket_number <> linked_number", name="not_itself"),
        Index(
            "uq_ticket_links_one_parent",
            "ticket_number",
            unique=True,
            postgresql_where=text("kind = 'parent'"),
        ),
    )

    ticket_number: Mapped[int] = mapped_column(
        ForeignKey(_FK, ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    linked_number: Mapped[int] = mapped_column(
        ForeignKey(_FK, ondelete="RESTRICT"), primary_key=True, index=True
    )
    # The order the links were written in, which a list of blockers keeps.
    position: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class TicketPullRequestRow(Base):
    """A ticket's pull request; the row exists only while the ticket has one."""

    __tablename__ = "ticket_pull_requests"
    __table_args__ = (
        CheckConstraint(f"state IN ({_quoted(PULL_REQUEST_STATES)})", name="known_state"),
        CheckConstraint("number > 0", name="positive_number"),
    )

    ticket_number: Mapped[int] = mapped_column(
        ForeignKey(_FK, ondelete="CASCADE"), primary_key=True
    )
    number: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TicketDocumentRow(Base):
    """One named document of a ticket, as markdown, with its version and last writer."""

    __tablename__ = "ticket_documents"

    ticket_number: Mapped[int] = mapped_column(
        ForeignKey(_FK, ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    body: Mapped[str] = mapped_column(Text)
    # Starts at 1 and rises by one on every write: a writer names the version it read, and a
    # write from an older one is refused instead of losing the change in between.
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    updated_by: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TicketMockFileRow(Base):
    """An image of a ticket's mock: its bytes and the type it is served as.

    A mock is drawn before the ticket is built and is read by the page, so it is a row of the
    ticket and not a file of its branch. The size limit is in `rules.MOCK_LIMIT`; the checks repeat
    `rules.check_mock`.
    """

    __tablename__ = "ticket_mock_files"
    __table_args__ = (
        CheckConstraint("name <> ''", name="has_name"),
        CheckConstraint("octet_length(data) >= 1", name="has_content"),
        CheckConstraint("octet_length(data) <= 16777216", name="within_size_limit"),
        CheckConstraint(f"content_type IN ({_quoted(MOCK_TYPES)})", name="known_content_type"),
        # Never SVG: opened as a page it can run script.
        CheckConstraint(r"name ~* '\.(png|jpe?g|gif|webp)$'", name="image_name"),
    )

    ticket_number: Mapped[int] = mapped_column(
        ForeignKey(_FK, ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    content_type: Mapped[str] = mapped_column(Text)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    updated_by: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TicketActivityRow(Base):
    """One record of a ticket's history. Append-only: a trigger refuses UPDATE and DELETE.

    `data` is jsonb because each of the many record kinds carries keys of its own (a stage move
    `from` and `to`, a check run its exit code and step times, a judged attempt a list of objects);
    columns would be mostly empty and change with every new kind. The ticket cannot be deleted
    while it has history (`RESTRICT`).
    """

    __tablename__ = "ticket_activity"
    __table_args__ = (
        Index("ix_ticket_activity_ticket_number", "ticket_number", "id"),
        Index("ix_ticket_activity_by", "by", "kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    ticket_number: Mapped[int] = mapped_column(ForeignKey(_FK, ondelete="RESTRICT"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(Text)
    # Who wrote it: the actor's subject (the owner, a run); '' for the board itself.
    by: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
