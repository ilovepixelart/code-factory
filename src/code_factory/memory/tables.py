"""The memory module's table. A migration in `alembic/versions` creates it.

Every column is NOT NULL: an optional text field is `''` when unset. An entry is active while
`retired` is empty; retiring it keeps the row (the history the Memory page lists) with the reason.
"""

from datetime import date, datetime
from typing import get_args

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Identity,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.memory.models import MemoryKind
from code_factory.platform.db.base import Base

_EMPTY = text("''")
KINDS = get_args(MemoryKind)


class MemoryEntryRow(Base):
    """One entry of a repository's memory; `name` (`<day>-<slug>`) is its id in the repository."""

    __tablename__ = "memory_entries"
    __table_args__ = (
        UniqueConstraint("repository", "name"),
        CheckConstraint(
            "kind IN (" + ", ".join(f"'{kind}'" for kind in KINDS) + ")", name="known_kind"
        ),
        CheckConstraint("statement <> ''", name="has_statement"),
        Index("ix_memory_entries_proposed_by", "proposed_by"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    repository: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    statement: Mapped[str] = mapped_column(Text)
    why: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    source: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    guard: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    scope: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    supersedes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    expires: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    until_ticket: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    cites: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    proposed: Mapped[bool] = mapped_column(server_default=text("false"))
    verdict: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    written_on: Mapped[date] = mapped_column(Date)
    reviewed: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    retired: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    merged_into: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    # The actor that recorded it (the owner, a run).
    created_by: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    # The actor that proposed it, kept after approval: what `count_proposed_by` counts.
    proposed_by: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
