"""The sessions module's tables. A migration in `alembic/versions` creates them.

The ledger (`session_events`, `session_rejects`, `session_spool_progress`) is derived from the
capture spool and can be rebuilt from it. `session_views` is derived from the ledger. None has a
foreign key: a session is the set of its events, and a row of a derived table is rebuilt, not
protected. `session_run_requests` belongs to the runs another module owns, so it holds the run id
as text.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base


class SessionEventRow(Base):
    """One captured hook event. `seq` is the stream's position and the id in URLs.

    `payload` is `json`, not `jsonb`: the key order of a payload is part of what the stream
    sends, and `jsonb` sorts keys. Nothing filters inside it in SQL.
    """

    __tablename__ = "session_events"
    __table_args__ = (
        UniqueConstraint("spool", "spool_offset", name="uq_session_events_spool_spool_offset"),
        Index("ix_session_events_session_id_seq", "session_id", "seq"),
    )

    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    session_id: Mapped[str] = mapped_column(Text)  # empty for an event that names no session
    agent_id: Mapped[str | None] = mapped_column(Text)
    event: Mapped[str] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    spool: Mapped[str] = mapped_column(Text)
    spool_offset: Mapped[int] = mapped_column(BigInteger)  # byte offset of the line in its spool
    payload: Mapped[dict[str, object]] = mapped_column(JSON)


class SessionRejectRow(Base):
    """A spool line that is no event: skipped once and kept, never retried."""

    __tablename__ = "session_rejects"
    __table_args__ = (
        UniqueConstraint("spool", "spool_offset", name="uq_session_rejects_spool_spool_offset"),
    )

    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    spool: Mapped[str] = mapped_column(Text)
    spool_offset: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text)
    head: Mapped[str] = mapped_column(Text)  # the first 200 bytes, lossy
    rejected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SessionSpoolProgressRow(Base):
    """Where the ingest stopped in each spool, advanced by compare-and-set."""

    __tablename__ = "session_spool_progress"
    __table_args__ = (CheckConstraint("byte_offset >= 0", name="byte_offset"),)

    spool: Mapped[str] = mapped_column(Text, primary_key=True)
    byte_offset: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SessionViewRow(Base):
    """The unsettled derivation of one session, updated in the ingest transaction.

    The clock is applied at read, never stored. `view` is `jsonb` because it is nested, read whole
    and never filtered inside; what a query filters on is a column. `window_seq` is the `seq` of
    the first event of the derivation window (the latest `SessionStart`).
    """

    __tablename__ = "session_views"
    __table_args__ = (
        Index("ix_session_views_last_event_at", text("last_event_at DESC")),
        Index("ix_session_views_state_last_event_at", "state", "last_event_at"),
    )

    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    state: Mapped[str] = mapped_column(Text)
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seq: Mapped[int] = mapped_column(BigInteger)
    window_seq: Mapped[int] = mapped_column(BigInteger)
    cwd: Mapped[str] = mapped_column(Text)
    repository: Mapped[str] = mapped_column(Text)
    branch: Mapped[str] = mapped_column(Text)
    transcript: Mapped[str] = mapped_column(Text)
    rules_version: Mapped[int] = mapped_column(Integer)
    view: Mapped[dict[str, object]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SessionRunRequestRow(Base):
    """One model request a run reported through its telemetry export."""

    __tablename__ = "session_run_requests"
    __table_args__ = (
        CheckConstraint("input_tokens >= 0", name="input_tokens"),
        CheckConstraint("output_tokens >= 0", name="output_tokens"),
        Index("ix_session_run_requests_run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    run_id: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(BigInteger)
    output_tokens: Mapped[int] = mapped_column(BigInteger)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
