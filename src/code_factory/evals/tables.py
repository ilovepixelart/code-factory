"""The evals module's tables: suite records, their task runs, judgements and judge-day claims.

No foreign key to another module's table: a record outlives the tickets and sessions it measured.
Scores are double precision: the report rounds half to even on the binary value.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base

_EMPTY = text("''")
_FALSE = text("false")
_ZERO = text("0")

_KIND_SCORES = (
    "(kind = 'build' AND pass_at_1 IS NOT NULL AND pass_k IS NOT NULL AND pass_at_k IS NOT NULL"
    " AND caught IS NULL AND false_findings IS NULL AND failed IS NULL)"
    " OR (kind = 'review' AND caught IS NOT NULL AND false_findings IS NOT NULL"
    " AND failed IS NOT NULL AND pass_at_1 IS NULL AND pass_k IS NULL AND pass_at_k IS NULL)"
)
_ROLE = (
    "(role = 'clean' AND passed IS NULL) OR (role <> 'clean' AND blocking IS NULL"
    " AND passed IS NOT NULL)"
)
_SHAPE = (
    "(kind = 'score' AND score IS NOT NULL AND scorer IS NULL AND answer IS NULL)"
    " OR (kind = 'answer' AND score IS NULL AND scorer IS NOT NULL AND answer IS NOT NULL)"
)


class EvalRecordRow(Base):
    """One suite run of one setup."""

    __tablename__ = "eval_records"
    __table_args__ = (
        CheckConstraint("kind IN ('build', 'review')", name="known_kind"),
        CheckConstraint("stage IN ('spec', 'build', 'review')", name="known_stage"),
        CheckConstraint("runs > 0", name="runs_positive"),
        CheckConstraint("cost >= 0", name="cost_not_negative"),
        CheckConstraint("tokens IS NULL OR tokens >= 0", name="tokens_not_negative"),
        CheckConstraint(_KIND_SCORES, name="kind_scores"),
        Index("ix_eval_records_set", "repository", "set_name", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    repository: Mapped[str] = mapped_column(Text)
    set_name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stage: Mapped[str] = mapped_column(Text)
    runtime: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    model: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    instructions: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    memory: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    lesson: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    agent: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    connection: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    runs: Mapped[int] = mapped_column(Integer)
    pass_at_1: Mapped[float | None] = mapped_column(Double, nullable=True)
    pass_k: Mapped[float | None] = mapped_column(Double, nullable=True)
    pass_at_k: Mapped[float | None] = mapped_column(Double, nullable=True)
    caught: Mapped[float | None] = mapped_column(Double, nullable=True)
    false_findings: Mapped[float | None] = mapped_column(Double, nullable=True)
    failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[float] = mapped_column(Double, server_default=_ZERO)
    tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class EvalTaskRunRow(Base):
    """One run of one task of a record."""

    __tablename__ = "eval_task_runs"
    __table_args__ = (
        CheckConstraint("role IN ('build', 'escape', 'clean')", name="known_role"),
        CheckConstraint("blocking IS NULL OR blocking >= 0", name="blocking_not_negative"),
        CheckConstraint(_ROLE, name="role_shape"),
    )

    record_id: Mapped[int] = mapped_column(
        ForeignKey("eval_records.id", ondelete="CASCADE"), primary_key=True
    )
    task_id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(Text)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    blocking: Mapped[int | None] = mapped_column(Integer, nullable=True)


class JudgementRow(Base):
    """A session's score from the judge, or a scorer's answer about it."""

    __tablename__ = "eval_judgements"
    __table_args__ = (
        CheckConstraint("kind IN ('score', 'answer')", name="known_kind"),
        CheckConstraint("score IS NULL OR score BETWEEN 1 AND 5", name="score_range"),
        CheckConstraint(
            "answer IS NULL OR answer IN ('yes', 'no', 'unclear')", name="known_answer"
        ),
        CheckConstraint("cost >= 0", name="cost_not_negative"),
        CheckConstraint("started_by IN ('owner', 'schedule')", name="known_starter"),
        CheckConstraint(_SHAPE, name="shape"),
        Index(
            "ix_eval_judgements_answers",
            "repository",
            "scorer",
            "at",
            postgresql_where=text("kind = 'answer'"),
        ),
        Index(
            "ix_eval_judgements_scheduled",
            "repository",
            "at",
            postgresql_where=text("started_by = 'schedule'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    repository: Mapped[str] = mapped_column(Text)
    session_id: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # Masked lines, shown only: an array, not jsonb.
    findings: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    scorer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    log: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    cost: Mapped[float] = mapped_column(Double, server_default=_ZERO)
    started_by: Mapped[str] = mapped_column(Text)


class JudgeDayRow(Base):
    """A scheduled judging of one repository on one UTC day, claimed once."""

    __tablename__ = "eval_judge_days"

    repository: Mapped[str] = mapped_column(Text, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
