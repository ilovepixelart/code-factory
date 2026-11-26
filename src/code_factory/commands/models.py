"""The commands module's shapes."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class Scope(StrEnum):
    """Which Claude Code settings file the hooks go into."""

    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


@dataclass(frozen=True)
class HookEntry:
    """One hook to install: its event, command, matcher, timeout and whether it runs async."""

    event: str
    command: str
    matcher: str = ""
    timeout: int | None = None
    asynchronous: bool = False


@dataclass(frozen=True)
class HookChange:
    """What install or uninstall did to a settings file."""

    path: Path
    changed: bool
    backup: Path | None = None


class TrackBody(BaseModel):
    """`path`: the absolute folder of a git repository, or of one of its worktrees."""

    model_config = ConfigDict(extra="forbid", strict=True)

    path: str
