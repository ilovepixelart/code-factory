"""The agents module's tables. A migration in `alembic/versions` creates them.

No column can hold a provider key: `connections.key_name` is only the name the operating
system's credential store keeps it under. Order is behaviour (the first agent of a column is tried
first), so `position` is a column, rewritten under an advisory lock with the rows locked.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.agents.models.constants import KIND_NAMES, ROLES, RUNTIMES
from code_factory.agents.rules.names import NAME_PATTERN
from code_factory.platform.db.base import Base

_EMPTY = sql_text("''")
_EMPTY_LIST = sql_text("'{}'")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class ConnectionRow(Base):
    """A model connection: where a kind of model server answers and the name of its key."""

    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint("name"),
        CheckConstraint(f"name ~ '{NAME_PATTERN}'", name="name"),
        CheckConstraint(f"kind IN ({_quoted(KIND_NAMES)})", name="kind"),
        Index("ix_connections_position", "position"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    base_url: Mapped[str] = mapped_column(Text)
    key_name: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    management_key_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRow(Base):
    """An agent: its runtime, connection, model, columns, takes, limits, prices and context.

    `roles`, `types` and `labels` are small ordered sets read and written whole with the agent,
    never queried singly. Ticket types are validated in the service against the tickets module's
    list, not by a check that would copy it.
    """

    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("name"),
        CheckConstraint(f"name ~ '{NAME_PATTERN}'", name="name"),
        CheckConstraint(f"runtime IN ({_quoted(RUNTIMES)})", name="runtime"),
        CheckConstraint(f"roles <@ ARRAY[{_quoted(ROLES)}]::text[]", name="roles"),
        CheckConstraint("max_tokens > 0", name="max_tokens"),
        CheckConstraint("max_seconds > 0", name="max_seconds"),
        CheckConstraint("(input_price IS NULL) = (output_price IS NULL)", name="prices_together"),
        CheckConstraint(
            "input_price >= 0 AND input_price < 'Infinity' "
            "AND output_price >= 0 AND output_price < 'Infinity'",
            name="prices",
        ),
        CheckConstraint("max_daily_usd > 0 AND max_daily_usd < 'Infinity'", name="max_daily_usd"),
        CheckConstraint("char_length(context) <= 8000", name="context_length"),
        CheckConstraint("(context IS NULL) = (context_at IS NULL)", name="context_time"),
        Index("ix_agents_position", "position"),
        Index("ix_agents_connection_id", "connection_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    runtime: Mapped[str] = mapped_column(Text)
    connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("connections.id", ondelete="RESTRICT")
    )
    model: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    roles: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=_EMPTY_LIST)
    types: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=_EMPTY_LIST)
    labels: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=_EMPTY_LIST)
    max_tokens: Mapped[int | None] = mapped_column(BigInteger)
    max_seconds: Mapped[int | None] = mapped_column(BigInteger)
    input_price: Mapped[float | None] = mapped_column(Double)
    output_price: Mapped[float | None] = mapped_column(Double)
    max_daily_usd: Mapped[float | None] = mapped_column(Double)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    context: Mapped[str | None] = mapped_column(Text)
    context_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContextVersionRow(Base):
    """A context an agent had before a change replaced it, at most 20 per agent.

    The service prunes in the write that adds one.

    `id` keys it so two changes in one second never collide; a restore by `at` takes the newest
    row with that `at`.
    """

    __tablename__ = "agent_context_versions"
    __table_args__ = (
        Index("ix_agent_context_versions_agent_id_at", "agent_id", sql_text("at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    context: Mapped[str] = mapped_column(Text)


class ModelCheckRow(Base):
    """An agent's one current model check, replaced by each check.

    It applies only while the agent still has the runtime, connection name and model it was
    taken with.
    """

    __tablename__ = "agent_model_checks"

    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    runtime: Mapped[str] = mapped_column(Text)
    connection: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    passed: Mapped[bool] = mapped_column(Boolean)
    problem: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
