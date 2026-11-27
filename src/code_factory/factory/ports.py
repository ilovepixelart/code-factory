"""What the factory reads from other modules, as protocols.

Each provider is one adapter in `code_factory.app` over the services of the module that owns the
facts, so the factory and the providers never import each other. Every method is bulk: one call
answers the whole range, never one call per pull request. A provider that cannot answer raises
`UnavailableError` with a sentence; a provider that is not built yet answers empty data with
`available = False` where the answer has that field.
"""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from code_factory.factory.models import (
    Improvements,
    OwnerTime,
    PullFact,
    RunCost,
    RunFact,
    ScorerCards,
)


@runtime_checkable
class RunsPort(Protocol):
    """Agent runs, board work and measurement work alike."""

    async def runs(self, since: float, until: float) -> list[RunFact]:
        """Runs started in `[since, until)`."""
        ...

    async def for_tickets(self, ticket_ids: Sequence[str]) -> list[RunFact]:
        """Every run of these tickets, whenever it started."""
        ...


@runtime_checkable
class PullsPort(Protocol):
    """Pull requests with their delivery facts."""

    async def in_range(self, since: float, until: float) -> list[PullFact]:
        """Pull requests opened or merged in `[since, until)`."""
        ...

    async def known_merge(self, ticket: str, url: str) -> bool:
        """Whether delivery recorded this exact pull request as merged for the ticket."""
        ...


@runtime_checkable
class CostPort(Protocol):
    """What runs cost."""

    async def costs(self, run_ids: Sequence[str]) -> dict[str, RunCost]:
        """The cost of each run it knows; ids it does not know are left out."""
        ...


class MeasurementSpendPort(Protocol):
    """The persisted spend of evaluations in an Analytics window."""

    async def recorded_spend(self, since: float, until: float) -> float | None:
        """Known measurement spend, or None while none of those runs has a recorded cost."""
        ...


@runtime_checkable
class ScorerPort(Protocol):
    """Scorer results."""

    async def cards(self, since: float, until: float) -> ScorerCards:
        """One card per scorer, counted over the smallest window it keeps that covers the range."""
        ...


@runtime_checkable
class ImprovementPort(Protocol):
    """Self-improvement pull requests."""

    async def newest(self, limit: int) -> Improvements:
        """The newest `limit` of them, newest first, whatever the range."""
        ...


class RepairsPort(Protocol):
    """The board's recorded repair requests for the PRs' tickets."""

    async def repair_requests(self, tickets: Sequence[str]) -> dict[str, list[float]]:
        """Request times by ticket, with an empty list for a known ticket without requests."""
        ...


class RoleNotesPort(Protocol):
    """Role notes and links to the findings the review carried forward."""

    async def role_note_outcomes(self, since: float, until: float) -> dict[str, tuple[int, int]]:
        """Note counts and fixed note counts by role for notes posted in this window."""
        ...


class OwnerTimePort(Protocol):
    """Owner-recorded active time, keyed by ticket and pull request URL."""

    async def record(self, ticket: str, entry: OwnerTime) -> None:
        """Record the current owner time of a merged pull request."""
        ...

    async def recorded(self, tickets: list[str]) -> dict[tuple[str, str], OwnerTime]:
        """Read the latest entry for each named ticket and pull request."""
        ...
