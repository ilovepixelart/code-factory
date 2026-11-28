"""What this module needs from the others, as protocols.

`module.py` wraps each owning module's service in a small adapter that renames its fields into
the values of `models.facts`, so this module and its providers never import each other's insides.
A provider that cannot answer raises `UnavailableError` with a sentence.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from code_factory.metrics.models import (
    CheckRecord,
    RunFacts,
    StepRun,
    TicketFlow,
    TrackedRepo,
)


class RepositoriesPort(Protocol):
    """The tracked repositories."""

    async def tracked(self) -> list[TrackedRepo]:
        """Every tracked repository and its checkout, with no call to git."""
        ...

    async def default_branch(self, name: str) -> str:
        """The default branch of the tracked repository `name`; it reads git, so a pass asks."""
        ...


class TicketsPort(Protocol):
    """The tickets' stages and moves."""

    async def flow_facts(
        self,
        repository: str,
        ids: Sequence[str] | None = None,
        stages: Sequence[str] | None = None,
        causes: Sequence[str] | None = None,
    ) -> list[TicketFlow]:
        """The repository's tickets, archived included.

        `ids` and `stages` narrow the answer; `causes` keeps the tickets that name one of these as
        their cause.
        """
        ...


class RunsPort(Protocol):
    """The agent runs."""

    async def since(self, since: datetime) -> list[RunFacts]:
        """Runs started at or after `since`, of every repository."""
        ...

    async def build_starts(
        self, repository: str, since: datetime, until: datetime
    ) -> dict[str, datetime]:
        """The first Build run start of each ticket inside `[since, until]`."""
        ...


class ChecksPort(Protocol):
    """The gate's records."""

    async def records(self, repository: str, tickets: Sequence[str]) -> list[CheckRecord]:
        """The check verdicts recorded for these tickets."""
        ...

    async def step_runs(
        self, newest: int | None, *, repository: str | None = None
    ) -> list[StepRun]:
        """The newest recorded gate runs with step results in the optional repository."""
        ...


@dataclass(frozen=True)
class MetricsPorts:
    """The four providers the service reads."""

    repositories: RepositoriesPort
    tickets: TicketsPort
    runs: RunsPort
    checks: ChecksPort
