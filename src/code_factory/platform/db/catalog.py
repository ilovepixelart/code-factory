"""The tables on `Base` as plain data, for the generated database reference."""

from dataclasses import dataclass

from sqlalchemy import Column, DefaultClause, Identity
from sqlalchemy.dialects import postgresql

from code_factory.platform.db.base import Base


@dataclass(frozen=True)
class ColumnShape:
    """A column: its PostgreSQL type, the default the database applies, and its keys."""

    name: str
    type: str
    nullable: bool
    default: str
    primary_key: bool
    references: tuple[str, ...]


@dataclass(frozen=True)
class TableShape:
    """A table, the package that declares it, the first line of its row class and its columns."""

    name: str
    owner: str
    summary: str
    columns: tuple[ColumnShape, ...]


def _default(column: Column[object]) -> str:
    """The default as SQL; `identity` for a generated identity; empty when there is none."""
    server_default = column.server_default
    if isinstance(server_default, Identity):
        return "identity"
    if isinstance(server_default, DefaultClause):
        arg = server_default.arg
        return arg if isinstance(arg, str) else str(arg.compile(dialect=postgresql.dialect()))
    return ""


def _column(column: Column[object]) -> ColumnShape:
    return ColumnShape(
        name=column.name,
        type=str(column.type.compile(dialect=postgresql.dialect())),
        nullable=bool(column.nullable),
        default=_default(column),
        primary_key=column.primary_key,
        references=tuple(key.target_fullname for key in column.foreign_keys),
    )


def describe_tables() -> list[TableShape]:
    """Every mapped table in the order it is defined; `owner` is `platform` or the module's name."""
    rows = {
        str(getattr(mapper.local_table, "name", "")): mapper.class_
        for mapper in Base.registry.mappers
    }
    shapes: list[TableShape] = []
    for name, table in Base.metadata.tables.items():
        row = rows.get(name)
        if row is None:
            continue
        summary = next(iter((row.__doc__ or "").strip().splitlines()), "")
        columns = tuple(_column(column) for column in table.columns)
        shapes.append(TableShape(name, row.__module__.split(".")[1], summary, columns))
    return shapes
