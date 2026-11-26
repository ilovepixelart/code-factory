"""The talk module's tables. A migration in `alembic/versions` creates them.

Text columns are NOT NULL, `''` when unset; a timestamp is NULL until the thing happens. Every
table hangs on a ticket by `ticket_number` and goes with it (`CASCADE`). The answers of a question
are append-only: the current one is the highest id, a replaced one stays as history.
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
    Text,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base
from code_factory.talk.models import Channel, Route

_FK = "tickets.number"

_EMPTY = sql_text("''")
CHANNELS = get_args(Channel)
ROUTES = get_args(Route)
POST_KINDS = ("comment", "message")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class QuestionRow(Base):
    """A question an agent asked on a ticket.

    `choices` is a jsonb list of `{text, recommended, reason}`, at most 8, always read and written
    whole with its question. Asking the same open question twice is one question.
    """

    __tablename__ = "talk_questions"
    __table_args__ = (
        CheckConstraint("char_length(text) between 1 and 1000", name="text_length"),
        Index("ix_talk_questions_ticket_number", "ticket_number", "id"),
        Index(
            "ix_talk_questions_open",
            "ticket_number",
            "id",
            postgresql_where=sql_text("answered_at IS NULL AND withdrawn_at IS NULL"),
        ),
        Index(
            "uq_talk_questions_open_text",
            "ticket_number",
            sql_text("md5(text)"),
            "document",
            unique=True,
            postgresql_where=sql_text("answered_at IS NULL AND withdrawn_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    ticket_number: Mapped[int] = mapped_column(ForeignKey(_FK, ondelete="CASCADE"))
    # A ticket document by name (`spec`), `''` for none.
    document: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    text: Mapped[str] = mapped_column(Text)
    several: Mapped[bool] = mapped_column(server_default=sql_text("false"))
    topic: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    choices: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=sql_text("'[]'::jsonb")
    )
    asked_by: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_by: Mapped[str] = mapped_column(Text, server_default=_EMPTY)


class AnswerRow(Base):
    """One answer to a question; append-only."""

    __tablename__ = "talk_question_answers"
    __table_args__ = (
        CheckConstraint(f"channel IN ({_quoted(CHANNELS)})", name="known_channel"),
        Index("ix_talk_question_answers_question_id", "question_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("talk_questions.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    picked: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=sql_text("'{}'"))
    by: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PostRow(Base):
    """The owner's words on a ticket: a comment, or a message for the running agent.

    Both are one table because only messages use the delivery columns and `route`.
    """

    __tablename__ = "talk_posts"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_quoted(POST_KINDS)})", name="known_kind"),
        CheckConstraint(f"route = '' OR route IN ({_quoted(ROUTES)})", name="known_route"),
        CheckConstraint("(kind = 'message') = (route <> '')", name="route_is_for_messages"),
        CheckConstraint(
            "kind = 'comment' OR (path = '' AND line IS NULL)", name="place_is_for_comments"
        ),
        Index("ix_talk_posts_ticket_number", "ticket_number", "id"),
        Index(
            "ix_talk_posts_pending",
            "ticket_number",
            postgresql_where=sql_text("kind = 'message' AND delivered_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    ticket_number: Mapped[int] = mapped_column(ForeignKey(_FK, ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    line: Mapped[int | None] = mapped_column(Integer)
    route: Mapped[str] = mapped_column(Text, server_default=_EMPTY)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_to: Mapped[str] = mapped_column(Text, server_default=_EMPTY)


class NewsMarkRow(Base):
    """How far the posts and answers reach that a running session was given."""

    __tablename__ = "talk_news_marks"

    ticket_number: Mapped[int] = mapped_column(
        ForeignKey(_FK, ondelete="CASCADE"), primary_key=True
    )
    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    post_id: Mapped[int] = mapped_column(BigInteger, server_default=sql_text("0"))
    answer_id: Mapped[int] = mapped_column(BigInteger, server_default=sql_text("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
