"""What a check reports, and what the settings module asks of the tickets module."""

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Protocol, override

from pydantic import BaseModel


@dataclass(frozen=True, order=True)
class Problem:
    """A file off its model: where, which line (0 for the whole file) and what."""

    path: str
    line: int
    message: str

    @override
    def __str__(self) -> str:
        """`path:line: message`."""
        return f"{self.path}:{self.line}: {self.message}"


@dataclass(frozen=True)
class ConfigReport:
    """The problems of a check, sorted by path and line.

    `notes` are expired entries a branch passes; `unchecked` names checks that could not run.
    """

    problems: tuple[Problem, ...] = ()
    notes: tuple[Problem, ...] = ()
    unchecked: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Whether nothing is wrong."""
        return not self.problems


@dataclass(frozen=True)
class ExceptionsReport:
    """What `exceptions.toml` check found.

    `notes` are expired entries a branch passes. `unchecked` names checks that could not run.
    """

    problems: tuple[Problem, ...] = ()
    notes: tuple[Problem, ...] = ()
    unchecked: tuple[str, ...] = field(default=())


class IntakeGrant(BaseModel):
    """The repository and address a tracker key was stored for."""

    key_name: str
    repository: str
    url: str


class TicketFacts(Protocol):
    """What the tickets module tells this one; it binds an implementation at startup."""

    async def existing(self, ids: Collection[str]) -> frozenset[str]:
        """The ids among `ids` that name a ticket."""
        ...

    async def sharing_branch(self, ticket_id: str) -> tuple[str, ...]:
        """The other tickets whose branch is the same as this ticket's, sorted."""
        ...


@dataclass(frozen=True)
class BoardSettings:
    """The board-wide settings: the cap on agent runs over all repositories, the days a prune keeps.

    None is a key never set; 0 is a value (a prune of 0 days keeps everything).
    """

    agent_slots: int | None = None
    prune_days: int | None = None


@dataclass(frozen=True)
class ReviewGuide:
    """A repository's review guide as its base branch commits it, and the ref it was read from."""

    base: str
    text: str
