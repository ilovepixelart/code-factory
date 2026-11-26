"""The repositories module's table. A migration in `alembic/versions` creates it."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base


class RepositoryRow(Base):
    """One tracked repository; the name is unique, so one folder name is one repository."""

    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("name"),
        CheckConstraint("name <> ''", name="has_name"),
        CheckConstraint("path LIKE '/%'", name="absolute_path"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
