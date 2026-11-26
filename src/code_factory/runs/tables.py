"""The runs module's tables: runs, the halt row, permission requests and their history, previews.

A run's log, exit file and sandbox file stay files in the state folder: they are streams and inputs
of other programs, not records. The model requests a run reported and the memory entries it was
given belong to the sessions and memory-extras modules (`session_run_requests`,
`memory_deliveries`).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base

_EMPTY = text("''")
_FALSE = text("false")
_STAGES = (
    "('spec', 'build', 'review', 'split', 'coordinate', 'qa', 'security', 'tests', 'read', "
    "'critique')"
)
_VERDICTS = "('allow', 'deny')"


_TZ = DateTime(timezone=True)


class RunRow(Base):
    """One run of an agent.

    `exit_code` null means active. `settled_at` is set after the end's side effects ran, so a crash
    between the end and its effects repeats them. `pid` is null between the insert and the spawn.
    """

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(f"stage IN {_STAGES}", name="known_stage"),
        CheckConstraint("permissions IN ('acceptEdits', 'bypassPermissions')", name="known_mode"),
        CheckConstraint("iteration >= 1", name="iteration_from_one"),
        CheckConstraint("attempt >= 0", name="attempt_not_negative"),
        # A database refuses a double start: one active run of a ticket and attempt, one active
        # coordinator of a repository.
        Index(
            "uq_runs_active_ticket_attempt",
            "ticket_id",
            "attempt",
            unique=True,
            postgresql_where=text("exit_code IS NULL AND ticket_id IS NOT NULL"),
        ),
        Index(
            "uq_runs_active_coordinator",
            "repository",
            unique=True,
            postgresql_where=text("stage = 'coordinate' AND exit_code IS NULL"),
        ),
        Index("ix_runs_ticket_started", "ticket_id", text("started_at DESC")),
        Index("ix_runs_started_at", "started_at"),
        Index("ix_runs_agent_started", "agent", text("started_at DESC")),
        Index("ix_runs_active", "id", postgresql_where=text("exit_code IS NULL")),
        Index(
            "ix_runs_unsettled",
            "settled_at",
            postgresql_where=text("exit_code IS NOT NULL AND settled_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    # Null for the coordinator and after the ticket is deleted: its cost stays in the month.
    ticket_id: Mapped[int | None] = mapped_column(
        ForeignKey("tickets.number", ondelete="SET NULL"), nullable=True
    )
    ticket_key: Mapped[str] = mapped_column(Text)
    repository: Mapped[str] = mapped_column(Text)
    branch: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    worktree: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    log: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    stage: Mapped[str] = mapped_column(Text)
    pid: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pid_started_at: Mapped[datetime | None] = mapped_column(_TZ, nullable=True)
    started_at: Mapped[datetime] = mapped_column(_TZ)
    # The start minus machine sleep, so a sleep does not count against the time limit.
    awake_started_at: Mapped[datetime | None] = mapped_column(_TZ, nullable=True)
    looping: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    permissions: Mapped[str] = mapped_column(Text, server_default=text("'acceptEdits'"))
    iteration: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    attempt: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    continued: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(_TZ, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(_TZ, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    cost_estimated: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cache_read: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    turns: Mapped[int | None] = mapped_column(Integer, nullable=True)
    halted: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    instructions: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    model: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    agent: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    connection: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    head: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    judged_head: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    tests_checked: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    uncommitted: Mapped[bool] = mapped_column(Boolean, server_default=_FALSE)
    # Null: no commits were recorded, which is not "made none".
    commits: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    limited_until: Mapped[datetime | None] = mapped_column(_TZ, nullable=True)
    resume_refused: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    context: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    context_at: Mapped[datetime | None] = mapped_column(_TZ, nullable=True)
    memory_digest: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentHaltRow(Base):
    """The singleton row that says every agent is stopped: present means halted."""

    __tablename__ = "agent_halt"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, server_default=text("1"))
    halted_at: Mapped[datetime] = mapped_column(_TZ)
    by: Mapped[str] = mapped_column(Text)


class PermissionRequestRow(Base):
    """A tool call an agent waits on. Answered rows are kept: suggestions are a query over them."""

    __tablename__ = "permission_requests"
    __table_args__ = (
        CheckConstraint("id ~ '^[0-9a-f]{12}$'", name="id_is_12_hex"),
        CheckConstraint("char_length(summary) <= 300", name="summary_at_most_300"),
        CheckConstraint(f"verdict IS NULL OR verdict IN {_VERDICTS}", name="known_verdict"),
        CheckConstraint(
            "status IN ('pending', 'answered', 'expired', 'withdrawn')", name="known_status"
        ),
        Index("ix_permission_requests_status_requested", "status", "requested_at"),
        Index(
            "ix_permission_requests_answered_kind",
            "kind",
            postgresql_where=text("status = 'answered'"),
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    repository: Mapped[str] = mapped_column(Text)
    ticket_key: Mapped[str] = mapped_column(Text)
    tool: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    # Null: no standing rule can cover the request.
    kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    requested_at: Mapped[datetime] = mapped_column(_TZ)
    verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(_TZ, nullable=True)
    answered_by: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))


class PermissionDecisionRow(Base):
    """One decision on a request: by the policy, the reviewer or the owner. Pruned after 90 days."""

    __tablename__ = "permission_decisions"
    __table_args__ = (
        CheckConstraint(f"decision IN {_VERDICTS}", name="known_decision"),
        CheckConstraint("by IN ('policy', 'reviewer', 'owner')", name="known_decider"),
        Index(
            "ix_permission_decisions_ticket_latest",
            "repository",
            "ticket_key",
            text("id DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    at: Mapped[datetime] = mapped_column(_TZ)
    repository: Mapped[str] = mapped_column(Text)
    ticket_key: Mapped[str] = mapped_column(Text)
    tool: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(Text)
    by: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, server_default=_EMPTY)


class PermissionReviewRow(Base):
    """One review of a request by the configured reviewer; the per-session tally is a count."""

    __tablename__ = "permission_reviews"
    __table_args__ = (
        CheckConstraint("verdict IN ('allow', 'deny', 'owner')", name="known_verdict"),
        Index("ix_permission_reviews_session", "session_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    at: Mapped[datetime] = mapped_column(_TZ)
    session_id: Mapped[str] = mapped_column(Text)
    ticket_key: Mapped[str] = mapped_column(Text)
    tool: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    input_sha256: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(Text)


class PermissionRuleRow(Base):
    """A standing rule the owner adopted; the order is `adopted_at`."""

    __tablename__ = "permission_rules"

    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    adopted_at: Mapped[datetime] = mapped_column(_TZ)


class RunPreviewRow(Base):
    """A ticket's running preview: one per ticket, by its key."""

    __tablename__ = "run_previews"
    __table_args__ = (
        CheckConstraint("pgid > 1", name="pgid_above_one"),
        CheckConstraint("port BETWEEN 1024 AND 65535", name="port_unprivileged"),
    )

    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.number", ondelete="CASCADE"), primary_key=True
    )
    repository: Mapped[str] = mapped_column(Text)
    pgid: Mapped[int] = mapped_column(BigInteger)
    pgid_started_at: Mapped[datetime] = mapped_column(_TZ)
    port: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(_TZ)
