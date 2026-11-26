"""The team module's tables: a ticket's claim and the runs recorded under it.

Claims are read by the runs, queue, board and runner paths in different processes and must
survive a restart for the 60 s a claim stays fresh, so they are rows, not memory. Nothing else is
stored: the Team page and the lanes are derived on read.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base


class TeamLeaseRow(Base):
    """A ticket's claim. The unique ticket is the guard against a double claim.

    `agent` is empty for the default agent and `runner:<name>` for a remote runner.
    """

    __tablename__ = "team_leases"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    ticket_number: Mapped[int] = mapped_column(
        ForeignKey("tickets.number", ondelete="CASCADE"), unique=True
    )
    agent: Mapped[str] = mapped_column(Text, server_default=text("''"), index=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    beat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TeamLeaseRunRow(Base):
    """A run recorded under a claim.

    There is no foreign key to the runs table, which another module owns: a claim may name a run
    that is not recorded, and a claim with only unrecorded runs holds while its beat is fresh.
    """

    __tablename__ = "team_lease_runs"

    lease_id: Mapped[int] = mapped_column(
        ForeignKey("team_leases.id", ondelete="CASCADE"), primary_key=True
    )
    run_id: Mapped[str] = mapped_column(Text, primary_key=True, index=True)
