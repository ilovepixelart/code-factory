"""What the team service's parts share: the unit of work, the ports, the clock, bounded reads."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import UnavailableError
from code_factory.team.adapters import GitFacts
from code_factory.team.models import TeamAgent, TeamRun
from code_factory.team.service.ports import TeamPorts

logger = logging.getLogger(__name__)

PORT_TIMEOUT = 10.0
DAY = 86_400.0


def utc_now() -> datetime:
    """The service's default clock."""
    return datetime.now(UTC)


@asynccontextmanager
async def together() -> AsyncGenerator[asyncio.TaskGroup]:
    """A task group whose first failure is raised as itself, not as an exception group."""
    try:
        async with asyncio.TaskGroup() as group:
            yield group
    except ExceptionGroup as failed:
        raise failed.exceptions[0] from None


async def fan_out[T](calls: Sequence[Awaitable[T]]) -> list[T]:
    """Await calls of one type together, in order; the first failure is raised as itself."""
    async with together() as group:
        tasks = [group.create_task(call) for call in calls]  # ty: ignore[invalid-argument-type]
    return [task.result() for task in tasks]


def merged(*lists: list[TeamRun]) -> list[TeamRun]:
    """The runs of every list once each, by id; a later list's copy of a run wins.

    List the copies with live usage last: `runs_on_ticket` reports tokens of a run still running,
    and the other sources may only know what was recorded.
    """
    return list({run.id: run for runs in lists for run in runs}.values())


class ServiceBase:
    """The unit of work, the lazily resolved ports, the clock and the git reads."""

    def __init__(
        self,
        uow: UnitOfWork,
        ports: Callable[[], TeamPorts],
        *,
        clock: Callable[[], datetime] = utc_now,
        git: GitFacts | None = None,
    ) -> None:
        self._uow = uow
        # One claim decision at a time in this process: waiters for the database lock would each
        # hold a pooled connection the lock holder's own reads need.
        self._serial = asyncio.Lock()
        self._ports_factory = ports
        self._clock = clock
        self._git = git

    def _seconds(self, now: float | None) -> float:
        return self._clock().timestamp() if now is None else now

    def _ports(self) -> TeamPorts:
        try:
            return self._ports_factory()
        except LookupError as missing:
            raise UnavailableError(f"the team cannot reach its sources: {missing}") from missing

    @staticmethod
    async def _read[T](name: str, call: Awaitable[T]) -> T:
        """A port read bounded by the port timeout."""
        try:
            async with asyncio.timeout(PORT_TIMEOUT):
                return await call
        except TimeoutError:
            msg = f"the team could not read {name}: no answer within {PORT_TIMEOUT:g} s"
            raise UnavailableError(msg) from None

    async def _runs_for(
        self,
        tickets: list[str],
        agents: list[TeamAgent],
        lease_runs: list[str],
        now: float,
        *,
        ports: TeamPorts,
    ) -> list[TeamRun]:
        """Every run a decision reads: the tickets', each agent's latest, today's, the claims'."""
        runs = ports.runs
        calls = [self._read("the runs", runs.latest_runs([agent.name for agent in agents]))]
        calls.append(self._read("the runs", runs.runs_since(now // DAY * DAY)))
        if lease_runs:
            calls.append(self._read("the runs", runs.runs_by_ids(lease_runs)))
        calls.extend(self._read("the runs", runs.runs_on_ticket(ticket)) for ticket in tickets)
        return merged(*await fan_out(calls))
