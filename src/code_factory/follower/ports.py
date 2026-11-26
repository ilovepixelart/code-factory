"""What the follower reads and drives in other modules, as protocols over its own shapes."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from code_factory.follower.models import ActiveRunFact, Card
from code_factory.follower.rules.queue import Rule


class Board(Protocol):
    """Tickets, stages, runs and settings as the queue reads them."""

    async def cards(self) -> list[Card]:
        """Every live ticket as a queue card."""
        ...

    async def active(self) -> list[ActiveRunFact]:
        """Runs with no exit."""
        ...

    async def slots(self) -> dict[str, int]:
        """Each tracked repository's `[agents] slots`."""
        ...

    async def overall(self) -> int | None:
        """The board's cap on runs over all repositories."""
        ...

    async def limits(self) -> dict[str, int]:
        """Each limited column's limit."""
        ...

    async def rule(self, ids: list[str]) -> Rule:
        """The team's say on each card."""
        ...


class Work(Protocol):
    """The loops of other modules a pass drives, and the run start."""

    async def collect(self) -> int:
        """End finished runs; how many."""
        ...

    async def keep(self) -> int:
        """Keep the team's leases; how many."""
        ...

    async def observe(self) -> int:
        """Observe the stages; how many tickets."""
        ...

    async def start(self, ticket_id: str, stage: str) -> None:
        """Start a run; a refusal raises a platform error with its sentence."""
        ...


class Filing(Protocol):
    """Tickets the board files by itself."""

    async def repositories(self) -> list[str]:
        """Every tracked repository."""
        ...

    async def recurring(self, repository: str) -> list[Mapping[str, object]]:
        """The repository's `[[recurring]]` entries."""
        ...

    async def sources(self, repository: str) -> set[str]:
        """The sources of the repository's tickets."""
        ...

    async def file(self, repository: str, fields: Mapping[str, object]) -> str:
        """File a ticket; its id."""
        ...

    async def failures(self, repository: str) -> list[Mapping[str, object]]:
        """The bug tickets a failing default branch and the reverted merges file, as fields."""
        ...

    async def scorer_firings(self, repository: str) -> list[Mapping[str, object]]:
        """The scorer tickets due, as fields."""
        ...


@dataclass(frozen=True)
class FollowerPorts:
    """Every port the follower uses."""

    board: Board
    work: Work
    filing: Filing
