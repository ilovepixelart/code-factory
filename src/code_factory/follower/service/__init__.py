"""The follower's public API: `FollowerService` and `QueueService`."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from code_factory.follower.models import PassReport, Planned
from code_factory.follower.ports import FollowerPorts
from code_factory.follower.repository import Leader, QueueRepository
from code_factory.follower.rules import NOT_STARTED, plan_queue, recurring_due
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import CodeFactoryError

logger = logging.getLogger(__name__)

STEP_S = 120.0
STEPS = (
    "collect",
    "keep_leases",
    "observe",
    "start_queued",
    "file_recurring",
    "file_scorers",
    "file_failures",
)


def utc_now() -> datetime:
    """Now, in UTC."""
    return datetime.now(UTC)


class QueueService:
    """The queue plan the board cards and the inbox read."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def plan(self) -> dict[str, str]:
        """Each queued ticket's note: `''` next up, the cap that holds it, or why it waits."""
        async with self._uow() as session:
            return await QueueRepository(session).plan()

    async def write(self, notes: dict[str, str], now: datetime) -> None:
        """Replace the plan, writing only what changed."""
        async with self._uow() as session:
            await QueueRepository(session).replace(notes, now)


class FollowerService:
    """The board loop: one leader per database runs the pass."""

    def __init__(
        self,
        uow: UnitOfWork,
        ports: FollowerPorts,
        queue: QueueService,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow = uow
        self._ports = ports
        self._queue = queue
        self._clock = clock
        self._wake = asyncio.Event()

    def wake(self) -> None:
        """Run the next pass now."""
        self._wake.set()

    async def run_pass(self, steps: tuple[str, ...] = STEPS) -> PassReport:
        """One pass, steps in order; a failing step is logged and the rest run."""
        report: dict[str, str] = {}
        for step in steps:
            work: Callable[[], Awaitable[str]] = getattr(self, f"_{step}")
            try:
                async with asyncio.timeout(STEP_S):
                    report[step] = await work()
            except (CodeFactoryError, TimeoutError, OSError) as error:
                logger.warning("follower: step %s failed: %s", step, error)
                report[step] = f"failed: {error}"
        return PassReport(steps=report)

    async def _collect(self) -> str:
        return f"{await self._ports.work.collect()} ended"

    async def _keep_leases(self) -> str:
        return f"{await self._ports.work.keep()} kept"

    async def _observe(self) -> str:
        return f"{await self._ports.work.observe()} observed"

    async def _start_queued(self) -> str:
        board = self._ports.board
        cards = await board.cards()
        plan = plan_queue(
            cards,
            await board.active(),
            slots=await board.slots(),
            overall=await board.overall(),
            limits=await board.limits(),
            rule=await board.rule([c.id for c in cards]),
            now=self._clock(),
        )
        stage = {card.id: card.run_stage or card.stage for card in cards}
        notes: dict[str, str] = {}
        started = 0
        for planned in plan:
            notes[planned.id] = await self._start(planned, stage[planned.id])
            started += 0 if notes[planned.id] else 1
        await self._queue.write(notes, self._clock())
        return f"{started} started of {len(plan)} planned"

    async def _start(self, planned: Planned, stage: str) -> str:
        if planned.reason:
            return planned.reason
        try:
            await self._ports.work.start(planned.id, stage)
        except CodeFactoryError as refused:
            return f"{NOT_STARTED}{refused}"
        return ""

    async def _file_recurring(self) -> str:
        filing, filed = self._ports.filing, 0
        for repository in await filing.repositories():
            entries = await filing.recurring(repository)
            if not entries:
                continue
            for fields in recurring_due(entries, await filing.sources(repository), self._clock()):
                await filing.file(repository, fields)
                filed += 1
        return f"{filed} filed"

    async def _file_scorers(self) -> str:
        filing, filed = self._ports.filing, 0
        for repository in await filing.repositories():
            for fields in await filing.scorer_firings(repository):
                await filing.file(repository, fields)
                filed += 1
        return f"{filed} filed"

    async def _file_failures(self) -> str:
        filing, filed = self._ports.filing, 0
        for repository in await filing.repositories():
            known = await filing.sources(repository)
            for fields in await filing.failures(repository):
                if fields["source"] in known:
                    continue
                await filing.file(repository, fields)
                known.add(str(fields["source"]))
                filed += 1
        return f"{filed} filed"

    async def run(self, every: float, lead: Callable[[], Awaitable[bool]]) -> None:
        """The long task: lead, pass, wait `every` seconds or a wake; never ends on its own."""
        while True:
            try:
                async with asyncio.timeout(STEP_S):
                    leading = await lead()
            except (CodeFactoryError, TimeoutError, OSError) as error:
                logger.warning("follower: leadership check failed: %s", error)
            else:
                if leading:
                    await self.run_pass()
            try:
                async with asyncio.timeout(max(every, 2.0)):
                    await self._wake.wait()
            except TimeoutError:
                pass
            self._wake.clear()


__all__ = ["FollowerService", "Leader", "QueueService"]
