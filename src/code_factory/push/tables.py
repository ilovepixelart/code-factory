"""The push module's tables: the target, what was sent, the last failure, the reply tokens.

A reply token is kept only as its SHA-256 digest, so a dump of the table answers nothing.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base

_TZ = DateTime(timezone=True)
_ONE = "id = 1"


class PushTargetRow(Base):
    """The one target messages go to, set by `code-factory push`."""

    __tablename__ = "push_targets"
    __table_args__ = (
        CheckConstraint(_ONE, name="one_row"),
        CheckConstraint("format in ('ntfy', 'webhook')", name="format_known"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    format: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    set_at: Mapped[datetime] = mapped_column(_TZ)


class PushSentRow(Base):
    """An item whose message was delivered, by its digest, while the item still waits."""

    __tablename__ = "push_sent"

    digest: Mapped[str] = mapped_column(Text, primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(_TZ)


class PushFailureRow(Base):
    """The last delivery that failed, kept until a pass fails nothing."""

    __tablename__ = "push_failures"
    __table_args__ = (CheckConstraint(_ONE, name="one_row"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    at: Mapped[datetime] = mapped_column(_TZ)
    problem: Mapped[str] = mapped_column(Text)


class ReplyTokenRow(Base):
    """A reply link: a permission request's id, or a question's identity (`request` empty)."""

    __tablename__ = "reply_tokens"
    __table_args__ = (
        CheckConstraint(
            "(request <> '') <> (jsonb_array_length(question) > 0)", name="request_or_question"
        ),
    )

    digest: Mapped[str] = mapped_column(Text, primary_key=True)
    request: Mapped[str] = mapped_column(Text, server_default=text("''"), index=True)
    question: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    minted_at: Mapped[datetime] = mapped_column(_TZ)
