"""Private inputs the owner records for Factory analytics."""

from sqlalchemy import BigInteger, CheckConstraint, Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.factory.models import MAX_SAFE_JSON_INT
from code_factory.platform.db import Base


class OwnerTimeRow(Base):
    """The active minutes and USD hourly rate recorded for one ticket's merged PR."""

    __tablename__ = "factory_owner_time"
    __table_args__ = (
        CheckConstraint(f"active_minutes BETWEEN 0 AND {MAX_SAFE_JSON_INT}", name="active_minutes"),
        CheckConstraint(
            f"hourly_rate_usd BETWEEN 0 AND {MAX_SAFE_JSON_INT}", name="hourly_rate_usd"
        ),
    )

    ticket_id: Mapped[str] = mapped_column(Text, primary_key=True)
    pull_url: Mapped[str] = mapped_column(Text, primary_key=True)
    active_minutes: Mapped[int] = mapped_column(BigInteger)
    hourly_rate_usd: Mapped[float] = mapped_column(Float)
