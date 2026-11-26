"""The `undo_entries` table: the stored inverse of one change, kept for seconds."""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db import Base


class UndoEntryRow(Base):
    """One offered undo. No foreign key: the payload names rows of several modules.

    `payload` is JSONB only because its shape differs per `kind`; its handler reads it whole and
    nothing filters on it in SQL.
    """

    __tablename__ = "undo_entries"
    __table_args__ = (
        CheckConstraint("kind <> ''", name="has_kind"),
        Index("ix_undo_entries_expires_at", "expires_at"),
    )

    token: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
