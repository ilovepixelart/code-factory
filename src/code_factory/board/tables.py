"""The `board_views` table: the filter and sort settings a person saved under a name."""

from sqlalchemy import BigInteger, CheckConstraint, Identity, Text
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db import Base


class BoardViewRow(Base):
    """One saved view: its name and the board's address query (`type=bug&sort=title`).

    The identity keeps the order they were saved in, which is the order the page lists them.
    """

    __tablename__ = "board_views"
    __table_args__ = (CheckConstraint("name <> ''", name="has_name"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    query: Mapped[str] = mapped_column(Text)
