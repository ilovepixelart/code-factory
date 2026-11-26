"""ORM models. A migration in `alembic/versions` creates each table; `create_all` is never used."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base

# Key policy: a table of many rows gets a `bigint` identity key (compact, ordered, no clock or
# randomness in the key); `schema_info` has exactly one row, so its key is a constant.


class SchemaInfo(Base):
    """The single row holding the data format version of the stored state.

    Alembic's revision says which tables exist; this version says which format the rows are in.
    A build refuses to start on a format it does not read (see `code_factory.platform.db.schema`).
    """

    __tablename__ = "schema_info"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    data_format_version: Mapped[int] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
