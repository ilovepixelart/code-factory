"""What the generated module map, feature map and table reference show."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandFacts:
    """A command as the feature map lists it: its name and its help sentence."""

    name: str
    help: str


@dataclass(frozen=True)
class ModuleFacts:
    """A module as the map lists it: what it is, and what it serves, runs and stores."""

    name: str
    summary: str
    routes: tuple[str, ...]
    commands: tuple[CommandFacts, ...]
    tools: bool
    background: bool
    tables: tuple[str, ...]


@dataclass(frozen=True)
class ColumnFacts:
    """A column as the database reference lists it; `references` is `table.column` or empty."""

    name: str
    type: str
    nullable: bool
    default: str
    primary_key: bool
    references: tuple[str, ...]


@dataclass(frozen=True)
class TableFacts:
    """A table, the module that owns it, the first line of its row class and its columns."""

    name: str
    module: str
    summary: str
    columns: tuple[ColumnFacts, ...]
