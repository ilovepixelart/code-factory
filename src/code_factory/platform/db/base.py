"""Declarative base. The naming convention makes every generated constraint name deterministic."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Every constraint gets a name derived from its table and columns, so a later migration can alter
# or drop it by a name known without asking the database. `ck` has no column to derive from: a
# check constraint is always given an explicit name, which fills `%(constraint_name)s`.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


class Base(DeclarativeBase):
    """Base of every ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
