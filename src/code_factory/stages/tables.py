"""The stages module's tables. A migration in `alembic/versions` creates each one.

A ticket is addressed by `ticket_number`, the key of the tickets table, and every row goes with its
ticket (`CASCADE`). Times are `timestamptz`. Every field is a column: nothing is jsonb.
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
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base
from code_factory.stages.models import RELEASED, Stage

_EMPTY = text("''")
_FALSE = text("false")
_FK = "tickets.number"
STAGES = (*(stage.value for stage in Stage), RELEASED)
FIX_REASONS = ("ci", "review", "conflict")
OUTCOMES = ("passed", "returned", "skipped")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class StageDeclarationRow(Base):
    """A column a person or an agent declared for a ticket; it wins over the derived one.

    The row exists only while a column is declared: a move onto the derived column deletes it.
    """

    __tablename__ = "stage_declarations"
    __table_args__ = (CheckConstraint(f"stage IN ({_quoted(STAGES)})", name="known_stage"),)

    ticket_number: Mapped[int] = mapped_column(
        ForeignKey(_FK, ondelete="CASCADE"), primary_key=True
    )
    stage: Mapped[str] = mapped_column(Text)
    by: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StageFactsRow(Base):
    """The git side of a ticket's evidence, one row per ticket, so a board read is database only.

    `known` false means git could not be read: nothing may act on the placement.
    """

    __tablename__ = "stage_facts"
    __table_args__ = (Index("ix_stage_facts_observed_at", "observed_at"),)

    ticket_number: Mapped[int] = mapped_column(
        ForeignKey(_FK, ondelete="CASCADE"), primary_key=True
    )
    branch: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    known: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    local: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    pushed: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    in_worktree: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    merged: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    has_commits: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    untraced: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    default_branch: Mapped[str] = mapped_column(Text, server_default=text("'main'"))
    head: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvidenceChangeRow(Base):
    """One row when a checklist item's presence differs from its last row.

    No row counts as absent.
    """

    __tablename__ = "evidence_changes"
    __table_args__ = (
        CheckConstraint(f"stage IN ({_quoted(STAGES)})", name="known_stage"),
        Index("ix_evidence_changes_ticket_stage", "ticket_number", "stage", desc("id")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    ticket_number: Mapped[int] = mapped_column(ForeignKey(_FK, ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(Text)
    present: Mapped[bool] = mapped_column(Boolean)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FixRoundRow(Base):
    """One fix round: one per failed head, one per review stamp.

    `run_id` (empty when no run gave it) has no foreign key: the runs belong to another module.
    """

    __tablename__ = "fix_rounds"
    __table_args__ = (
        CheckConstraint(f"reason IN ({_quoted(FIX_REASONS)})", name="known_reason"),
        UniqueConstraint(
            "ticket_number", "reason", "head", "review", name="uq_fix_rounds_round_given"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    ticket_number: Mapped[int] = mapped_column(ForeignKey(_FK, ondelete="CASCADE"), index=True)
    head: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    review: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    run_id: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FixHaltRow(Base):
    """That the rounds ran out, recorded once per head and reason."""

    __tablename__ = "fix_halts"
    __table_args__ = (
        CheckConstraint("rounds >= 0", name="rounds_not_negative"),
        UniqueConstraint("ticket_number", "head", "reason", name="uq_fix_halts_halt_recorded"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    ticket_number: Mapped[int] = mapped_column(ForeignKey(_FK, ondelete="CASCADE"), index=True)
    head: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    rounds: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FixWaitRow(Base):
    """The step a head failed on that main fails too; the latest write wins."""

    __tablename__ = "fix_waits"

    ticket_number: Mapped[int] = mapped_column(
        ForeignKey(_FK, ondelete="CASCADE"), primary_key=True
    )
    head: Mapped[str] = mapped_column(Text, primary_key=True)
    step: Mapped[str] = mapped_column(Text)
    main_commit: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewVerdictRow(Base):
    """A review decision of the board: passed, returned or skipped (`note` says why)."""

    __tablename__ = "review_verdicts"
    __table_args__ = (
        CheckConstraint(f"outcome IN ({_quoted(OUTCOMES)})", name="known_outcome"),
        Index("ix_review_verdicts_ticket_id", "ticket_number", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    ticket_number: Mapped[int] = mapped_column(ForeignKey(_FK, ondelete="CASCADE"))
    run_id: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    outcome: Mapped[str] = mapped_column(Text)
    head: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    reason: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    note: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
