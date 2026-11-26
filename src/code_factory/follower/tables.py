"""The follower's table: the last queue plan per ticket (`''` when next up)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base


class QueuePlanRow(Base):
    """A queued ticket's note: the cap that holds it, empty when it starts next."""

    __tablename__ = "follower_queue_plan"

    ticket_number: Mapped[int] = mapped_column(
        ForeignKey("tickets.number", ondelete="CASCADE"), primary_key=True
    )
    note: Mapped[str] = mapped_column(Text, server_default=text("''"))
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
