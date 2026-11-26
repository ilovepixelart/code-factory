"""The memory-extras table. A migration in `alembic/versions` creates it.

`run_id` carries no foreign key: the runs table belongs to a later module, which adds its own
with `ON DELETE CASCADE`. Entries are retired, never deleted, so the cascade from an entry fires
only when one is purged.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    Text,
    desc,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base


class MemoryDeliveryRow(Base):
    """An entry a run was given when its rules were delivered.

    `left_out` marks an entry that was loaded but cut by the budget. `ticket_id` is kept so the
    Memory page needs no join with runs.
    """

    __tablename__ = "memory_deliveries"
    __table_args__ = (
        PrimaryKeyConstraint("run_id", "repository", "entry_id"),
        ForeignKeyConstraint(
            ["repository", "entry_id"],
            ["memory_entries.repository", "memory_entries.name"],
            ondelete="CASCADE",
        ),
        Index("ix_memory_deliveries_entry", "repository", "entry_id", desc("delivered_at")),
        Index("ix_memory_deliveries_run_id", "run_id"),
    )

    run_id: Mapped[str] = mapped_column(Text)
    repository: Mapped[str] = mapped_column(Text)
    entry_id: Mapped[str] = mapped_column(Text)
    ticket_id: Mapped[str] = mapped_column(Text)
    left_out: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
