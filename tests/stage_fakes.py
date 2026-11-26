"""Fakes for the stage service tests: a clock and the git facts reader, each holding its answers."""

import asyncio
from collections.abc import Mapping
from datetime import datetime, timedelta

from code_factory.stages.models import BranchFacts
from stage_values import NOW


class FakeClock:
    """A settable clock."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakeFacts:
    """Answers each ticket's facts from `answers`; a ticket not listed is unreadable.

    `calls` records the repositories read, `failing` makes every read raise, and a read finding
    `hold` set answers what was known when it began, once `hold` is set.
    """

    def __init__(self) -> None:
        self.answers: dict[str, BranchFacts] = {}
        self.calls: list[str] = []
        self.seen: asyncio.Queue[str] = asyncio.Queue()
        self.failing = False
        self.hold: asyncio.Event | None = None
        self.reading: asyncio.Queue[str] = asyncio.Queue()

    def give(self, ticket: str, **facts: object) -> None:
        self.answers[ticket] = BranchFacts.model_validate({"known": True, **facts})

    async def read(self, repository: str, tickets: Mapping[str, str]) -> dict[str, BranchFacts]:
        self.calls.append(repository)
        self.seen.put_nowait(repository)
        if self.failing:
            msg = "git is gone"
            raise RuntimeError(msg)
        found = {t: self.answers.get(t, BranchFacts(known=False)) for t in tickets}
        if self.hold is not None:
            self.reading.put_nowait(repository)
            await self.hold.wait()
        return found
