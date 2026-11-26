"""Fakes for the ports of modules that are not built yet: they answer what the test sets."""

from collections.abc import Sequence
from datetime import datetime

from code_factory.board.models import (
    ActivityRecord,
    CheckRecord,
    PullFacts,
    RunRecord,
    TicketRuns,
)


class FakeRuns:
    """`CardRuns` over a dictionary; `month_cost` answers every window."""

    def __init__(
        self,
        runs: dict[str, TicketRuns] | None = None,
        records: dict[str, RunRecord] | None = None,
        month_cost: float = 0.0,
    ) -> None:
        self.runs = runs or {}
        self.records = records or {}
        self.month_cost = month_cost
        self.windows: list[tuple[str, datetime, datetime]] = []
        self.asked: list[str] = []

    async def card_runs(self, ticket_ids: Sequence[str]) -> dict[str, TicketRuns]:
        self.asked.extend(ticket_ids)
        return {i: self.runs[i] for i in ticket_ids if i in self.runs}

    async def run_records(self, run_ids: Sequence[str]) -> dict[str, RunRecord]:
        return {i: self.records[i] for i in run_ids if i in self.records}

    async def cost_between(self, repository: str, start: datetime, end: datetime) -> float:
        self.windows.append((repository, start, end))
        return self.month_cost


class FakeChecks:
    """`CardChecks` over a dictionary of records, oldest first."""

    def __init__(
        self,
        records: dict[str, list[CheckRecord]] | None = None,
        log: str = "",
        running: bool = False,
    ) -> None:
        self.records = records or {}
        self.log = log
        self.is_running = running
        self.log_asked: list[tuple[str, int]] = []

    async def latest_checks(self, ticket_ids: Sequence[str]) -> dict[str, list[CheckRecord]]:
        return {i: self.records[i] for i in ticket_ids if i in self.records}

    async def running(self, ticket_ids: Sequence[str]) -> set[str]:
        return set(ticket_ids) if self.is_running else set()

    async def log_tail(self, ticket_id: str, lines: int) -> str:
        self.log_asked.append((ticket_id, lines))
        return self.log


class FakeDelivery:
    """`CardDelivery` over dictionaries."""

    def __init__(
        self,
        pulls: dict[str, PullFacts] | None = None,
        events: dict[str, list[ActivityRecord]] | None = None,
    ) -> None:
        self.pull_facts = pulls or {}
        self.records = events or {}

    async def pulls(self, ticket_ids: Sequence[str]) -> dict[str, PullFacts]:
        return {i: self.pull_facts[i] for i in ticket_ids if i in self.pull_facts}

    async def events(self, ticket_ids: Sequence[str]) -> dict[str, list[ActivityRecord]]:
        return {i: self.records[i] for i in ticket_ids if i in self.records}


class FakeQueue:
    """`CardQueue` over a plan and holders."""

    def __init__(
        self, plan: dict[str, str] | None = None, holders: dict[str, str] | None = None
    ) -> None:
        self.plan = plan or {}
        self.held = holders or {}

    async def queue_plan(self) -> dict[str, str]:
        return self.plan

    async def holders(self, ticket_ids: Sequence[str]) -> dict[str, str]:
        return {i: self.held[i] for i in ticket_ids if i in self.held}


class FakeLimits:
    """`ColumnLimits` over a dictionary."""

    def __init__(self, limits: dict[str, int]) -> None:
        self.limits = limits

    async def column_limits(self) -> dict[str, int]:
        return self.limits
