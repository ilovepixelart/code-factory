"""What the board reads through ports: runs, checks, pull requests, the queue and column limits.

Each port answers in the shapes of `board.models`. The runs, checks, delivery, metrics and
ticket-writes modules register their adapter under the port's class (`board.service` exports
them); the queue is the board's own, over the team. Every method is one bulk read, never one per
ticket.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from code_factory.board.models import ActivityRecord, CheckRecord, PullFacts, RunRecord, TicketRuns


class CardRuns(Protocol):
    """The runs of tickets."""

    async def card_runs(self, ticket_ids: Sequence[str]) -> dict[str, TicketRuns]:
        """The runs of each ticket that has any; a ticket with none is absent."""
        ...

    async def run_records(self, run_ids: Sequence[str]) -> dict[str, RunRecord]:
        """What each run received, for the runs that recorded it."""
        ...

    async def cost_between(self, repository: str, start: datetime, end: datetime) -> float:
        """The cost of the repository's runs started in `[start, end)`; no cost counts as 0."""
        ...


class CardChecks(Protocol):
    """The checks of tickets."""

    async def latest_checks(self, ticket_ids: Sequence[str]) -> dict[str, list[CheckRecord]]:
        """Each ticket's check records, oldest first."""
        ...

    async def running(self, ticket_ids: Sequence[str]) -> set[str]:
        """The tickets whose checks run now."""
        ...

    async def log_tail(self, ticket_id: str, lines: int) -> str:
        """The last `lines` lines of the ticket's latest check log."""
        ...


class CardDelivery(Protocol):
    """The pull requests of tickets and the delivery records of their history."""

    async def pulls(self, ticket_ids: Sequence[str]) -> dict[str, PullFacts]:
        """What the delivery module knows of each ticket's pull request."""
        ...

    async def events(self, ticket_ids: Sequence[str]) -> dict[str, list[ActivityRecord]]:
        """Each ticket's delivery records, oldest first."""
        ...


class MergeLedger(Protocol):
    """When tickets' work landed on their default branch, as the Flow page counts it."""

    async def merged_at(self, ticket_ids: Sequence[str]) -> dict[str, float]:
        """Each ticket's first merge that was not reverted; a ticket with none is absent."""
        ...


class CardQueue(Protocol):
    """The follower's queue and the claims on tickets."""

    async def queue_plan(self) -> dict[str, str]:
        """The reason each queued ticket waits for, by ticket id; empty text means next."""
        ...

    async def holders(self, ticket_ids: Sequence[str]) -> dict[str, str]:
        """The agent holding each claimed ticket."""
        ...


class ColumnLimits(Protocol):
    """The board's limits on how many cards a column holds."""

    async def column_limits(self) -> dict[str, int]:
        """The limit of each column that has one."""
        ...
