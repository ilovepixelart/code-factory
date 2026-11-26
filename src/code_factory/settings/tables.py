"""The settings module's one table: which repository and address a tracker key may serve.

Everything else of this module is a file in a tracked repository.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db import Base


class IntakeKeyGrant(Base):
    """A tracker key and the one repository and address it may be sent to.

    `repository` is the root path as text, compared with the root a caller passes; it has no
    foreign key, because the module that tracks repositories is not this one and a grant must
    survive an untrack. `url` is stored without a trailing `/`.
    """

    __tablename__ = "intake_key_grants"
    __table_args__ = (
        CheckConstraint("key_name ~ '^CODE_FACTORY_INTAKE_[A-Z0-9_]+$'", name="key_name"),
        CheckConstraint("url ~ '^https?://'", name="url"),
    )

    key_name: Mapped[str] = mapped_column(Text, primary_key=True)
    repository: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


BOARD_SETTING_KEYS = ("agent_slots", "prune_days")


class BoardSetting(Base):
    """One board-wide whole-number setting; a key with no row is unset."""

    __tablename__ = "board_settings"
    __table_args__ = (
        CheckConstraint("key IN ('agent_slots', 'prune_days')", name="key"),
        CheckConstraint("value >= 0", name="value"),
    )

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[int] = mapped_column(Integer)
