"""The checks module's tables. A migration in `alembic/versions` creates each one.

Times are `timestamptz`; every field is a column. `check_runs` has no foreign key: its `subject`
may be `main`, and a ticket's history is pruned by age.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.checks.models import Containment, RunState, Scope, Verdict
from code_factory.platform.db.base import Base

_EMPTY = text("''")
_ACTIVE = (RunState.QUEUED.value, RunState.RUNNING.value)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


# Literal, never bound: a parameter in ON CONFLICT ... WHERE stops a generic plan from matching
# the partial index, and asyncpg's prepared statements switch to one after a few runs.
ONE_ACTIVE_WHERE = f"state IN ({_quoted(_ACTIVE)})"


class CheckRunRow(Base):
    """One run of the checks: the queue, the container turn and the heartbeat in one row."""

    __tablename__ = "check_runs"
    __table_args__ = (
        CheckConstraint(f"scope IN ({_quoted(tuple(s.value for s in Scope))})", name="known_scope"),
        CheckConstraint(
            f"state IN ({_quoted(tuple(s.value for s in RunState))})", name="known_state"
        ),
        CheckConstraint(
            f"contained IN ({_quoted(tuple(c.value for c in Containment))})",
            name="known_containment",
        ),
        CheckConstraint(
            f"verdict IN ({_quoted(tuple(v.value for v in Verdict))})", name="known_verdict"
        ),
        CheckConstraint(
            "(state = 'finished') = (verdict IS NOT NULL)", name="verdict_when_finished"
        ),
        Index(
            "ix_check_runs_one_active_per_subject",
            "repository",
            "subject",
            unique=True,
            postgresql_where=text(ONE_ACTIVE_WHERE),
        ),
        Index("ix_check_runs_subject_newest", "repository", "subject", desc("id")),
        Index("ix_check_runs_state_beat_at", "state", "beat_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    repository: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text)
    commit: Mapped[str] = mapped_column(Text)
    tree_id: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    state: Mapped[str] = mapped_column(Text)
    contained: Mapped[str] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(Text)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    beat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    verdict: Mapped[str | None] = mapped_column(Text)
    log_path: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    workspace: Mapped[str] = mapped_column(Text, server_default=_EMPTY)


class CheckMainRecordRow(Base):
    """The latest run on a repository's default branch, upserted."""

    __tablename__ = "check_main_records"
    __table_args__ = (CheckConstraint("exit_code > -1000", name="exit_code_plausible"),)

    repository: Mapped[str] = mapped_column(Text, primary_key=True)
    commit: Mapped[str] = mapped_column(Text)
    exit_code: Mapped[int] = mapped_column(Integer)
    log_path: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    step: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    passed: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    broken_by: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    searched: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    reason: Mapped[str] = mapped_column(Text, server_default=_EMPTY)


class CheckClaimRow(Base):
    """A remote runner's claim on one head of one ticket (or `main`)."""

    __tablename__ = "check_claims"
    __table_args__ = (
        UniqueConstraint(
            "repository", "subject", "head", name="uq_check_claims_one_claim_per_head"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    repository: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    head: Mapped[str] = mapped_column(Text)
    holder: Mapped[str] = mapped_column(Text)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    beat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CheckOfferRow(Base):
    """A runner's ask; it counts as an offer for 600 s. An array: it is only read as a set."""

    __tablename__ = "check_offers"

    runner: Mapped[str] = mapped_column(Text, primary_key=True)
    repositories: Mapped[list[str]] = mapped_column(ARRAY(Text))
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CheckDeclineRow(Base):
    """A head a runner gave back: the board runs it itself, for 24 h."""

    __tablename__ = "check_declines"
    __table_args__ = (Index("ix_check_declines_declined_at", "declined_at"),)

    repository: Mapped[str] = mapped_column(Text, primary_key=True)
    subject: Mapped[str] = mapped_column(Text, primary_key=True)
    head: Mapped[str] = mapped_column(Text, primary_key=True)
    declined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CheckVerifyRunRow(Base):
    """One hourly run of `[release] verify`; the newest 200 per repository are kept."""

    __tablename__ = "check_verify_runs"
    __table_args__ = (Index("ix_check_verify_runs_repository_id", "repository", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    repository: Mapped[str] = mapped_column(Text)
    release: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exit_code: Mapped[int] = mapped_column(Integer)
    log_path: Mapped[str] = mapped_column(Text)
    ticket_id: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
