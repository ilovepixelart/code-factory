"""In-memory providers of the five ports: each fails until told what it holds, and records calls."""

from collections.abc import Sequence
from typing import Any

from code_factory.factory.models import (
    Improvements,
    OwnerTime,
    PullFact,
    RunCost,
    RunFact,
    ScorerCards,
)
from code_factory.platform.errors import UnavailableError


class _Fake:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.refuses: str | None = None

    def _record(self, name: str, *args: object) -> None:
        self.calls.append((name, args))
        if self.refuses is not None:
            raise UnavailableError(self.refuses)


def _told[T](name: str, held: T | None) -> T:
    if held is None:
        msg = f"{name} was asked for something it was not told it holds"
        raise AssertionError(msg)
    return held


class FakeRuns(_Fake):
    def __init__(self) -> None:
        super().__init__()
        self.held: list[RunFact] | None = None

    def holding(self, runs: Sequence[RunFact]) -> FakeRuns:
        self.held = list(runs)
        return self

    async def runs(self, since: float, until: float) -> list[RunFact]:
        self._record("runs", since, until)
        return [r for r in _told("FakeRuns", self.held) if since <= r.started_at < until]

    async def for_tickets(self, ticket_ids: Sequence[str]) -> list[RunFact]:
        self._record("for_tickets", tuple(ticket_ids))
        return [r for r in _told("FakeRuns", self.held) if r.ticket_id in ticket_ids]


class FakePulls(_Fake):
    def __init__(self) -> None:
        super().__init__()
        self.held: list[PullFact] | None = None

    def holding(self, pulls: Sequence[PullFact]) -> FakePulls:
        self.held = list(pulls)
        return self

    async def opened(self, since: float, until: float) -> list[PullFact]:
        self._record("opened", since, until)
        return [p for p in _told("FakePulls", self.held) if since <= p.opened_at < until]

    async def merged(self, since: float, until: float) -> list[PullFact]:
        self._record("merged", since, until)
        return [
            p
            for p in _told("FakePulls", self.held)
            if p.merged_at is not None and since <= p.merged_at < until
        ]

    async def known_merge(self, ticket: str, url: str) -> bool:
        self._record("known_merge", ticket, url)
        return any(
            p.ticket_id == ticket and p.url == url and p.merged_at is not None
            for p in _told("FakePulls", self.held)
        )


class FakeCosts(_Fake):
    def __init__(self) -> None:
        super().__init__()
        self.held: dict[str, RunCost] | None = None

    def holding(self, costs: dict[str, RunCost]) -> FakeCosts:
        self.held = dict(costs)
        return self

    async def costs(self, run_ids: Sequence[str]) -> dict[str, RunCost]:
        self._record("costs", tuple(run_ids))
        held = _told("FakeCosts", self.held)
        return {i: held[i] for i in run_ids if i in held}


class FakeScorers(_Fake):
    def __init__(self) -> None:
        super().__init__()
        self.held: ScorerCards | None = None

    def holding(self, cards: ScorerCards) -> FakeScorers:
        self.held = cards
        return self

    async def cards(self, since: float, until: float) -> ScorerCards:
        self._record("cards", since, until)
        return _told("FakeScorers", self.held)


class FakeImprovements(_Fake):
    def __init__(self) -> None:
        super().__init__()
        self.held: Improvements | None = None

    def holding(self, improvements: Improvements) -> FakeImprovements:
        self.held = improvements
        return self

    async def newest(self, limit: int) -> Improvements:
        self._record("newest", limit)
        held = _told("FakeImprovements", self.held)
        return Improvements(available=held.available, items=held.items[:limit])


class FakeOwnerTime(_Fake):
    def __init__(self) -> None:
        super().__init__()
        self.entries: dict[tuple[str, str], OwnerTime] = {}

    async def record(self, ticket: str, entry: OwnerTime) -> None:
        self._record("record", ticket, entry)
        self.entries[ticket, entry.pull_url] = entry

    async def recorded(self, tickets: list[str]) -> dict[tuple[str, str], OwnerTime]:
        self._record("recorded", tuple(tickets))
        return {key: entry for key, entry in self.entries.items() if key[0] in tickets}
