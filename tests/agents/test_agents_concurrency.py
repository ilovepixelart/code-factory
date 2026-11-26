"""The agents service under real concurrency: pooled, committed sessions, as two requests would
have. The shared fixtures run on one rolled-back connection, where an advisory lock is re-entrant
and no two transactions overlap, so these tests commit and clean up the rows of their own names."""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import override

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from agents_support import Unfrozen
from code_factory.agents.adapters.probe import ModelProbe
from code_factory.agents.models.agents import AgentChange
from code_factory.agents.models.connections import ConnectionChange, Silence
from code_factory.agents.repository import RosterLock
from code_factory.agents.rules.model_checks import Request
from code_factory.agents.service import AgentService
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine, lock_key
from code_factory.platform.errors import ConflictError

WAIT_S = 5
HELD_S = 0.2
TOOL = json.dumps(
    {"model": "m-1", "content": [{"type": "tool_use", "name": "add", "input": {"a": 2, "b": 3}}]}
)


@pytest.fixture
async def engine(settings: Settings, migrated: None) -> AsyncGenerator[AsyncEngine]:  # noqa: ARG001
    pooled = create_engine(settings)
    try:
        yield pooled
    finally:
        await pooled.dispose()


@pytest.fixture
def prefix() -> str:
    return f"cc-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
async def cleaned(engine: AsyncEngine, prefix: str) -> AsyncGenerator[None]:
    yield
    async with engine.begin() as connection:
        await connection.execute(text("delete from agents where name like :p"), {"p": f"{prefix}%"})
        await connection.execute(
            text("delete from connections where name like :p"), {"p": f"{prefix}%"}
        )


def service(engine: AsyncEngine, probe: ModelProbe | None = None) -> AgentService:
    return AgentService(UnitOfWork(async_sessionmaker(engine, expire_on_commit=False)), probe=probe)


async def test_a_roster_write_waits_while_another_transaction_holds_the_roster_lock(
    engine: AsyncEngine, prefix: str
) -> None:
    agents = service(engine)
    async with async_sessionmaker(engine)() as holder, holder.begin():
        await RosterLock(holder).take()
        adding = asyncio.create_task(agents.add_agent(AgentChange(name=f"{prefix}-a")))
        await asyncio.sleep(HELD_S)
        assert not adding.done()
    async with asyncio.timeout(WAIT_S):
        assert (await adding).notice == f"Added {prefix}-a"


async def test_two_adds_of_one_name_give_one_agent_and_one_conflict(
    engine: AsyncEngine, prefix: str
) -> None:
    agents = service(engine)
    outcomes = await asyncio.gather(
        agents.add_agent(AgentChange(name=f"{prefix}-a")),
        agents.add_agent(AgentChange(name=f"{prefix}-a")),
        return_exceptions=True,
    )
    assert sorted(type(outcome).__name__ for outcome in outcomes) == ["Changed", "ConflictError"]
    conflict = next(o for o in outcomes if isinstance(o, ConflictError))
    assert str(conflict) == f"an agent named {prefix}-a is defined"


class CountingProbe(ModelProbe):
    """A probe that answers every request after a pause, counting the requests in flight."""

    def __init__(self) -> None:
        super().__init__()
        self.in_flight = 0
        self.peak = 0

    @override
    async def ask(self, request: Request) -> tuple[int, str] | Silence:
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await asyncio.sleep(HELD_S)
            return 200, TOOL
        finally:
            self.in_flight -= 1


async def agents_on_one_server(agents: AgentService, prefix: str, count: int) -> list[str]:
    await agents.add_connection(
        ConnectionChange(name=f"{prefix}-gw", kind="custom", base_url="http://127.0.0.1:9")
    )
    names = []
    for number in range(count):
        name = f"{prefix}-{number}"
        await agents.add_agent(
            AgentChange(name=name, connection=f"{prefix}-gw", model=f"m-{prefix}-{number}")
        )
        names.append(name)
    return names


async def test_the_checks_of_one_agent_run_one_after_the_other(
    engine: AsyncEngine, prefix: str
) -> None:
    probe = CountingProbe()
    agents = service(engine, probe)
    (name,) = await agents_on_one_server(agents, prefix, 1)
    async with asyncio.timeout(WAIT_S):
        await asyncio.gather(agents.check_model(name), agents.check_model(name))
    assert probe.peak == 1


async def test_at_most_two_checks_probe_at_once(engine: AsyncEngine, prefix: str) -> None:
    probe = CountingProbe()
    agents = service(engine, probe)
    names = await agents_on_one_server(agents, prefix, 3)
    async with asyncio.timeout(WAIT_S):
        await asyncio.gather(*(agents.check_model(name) for name in names))
    assert probe.peak == 2


class LockTakingProbe(ModelProbe):
    """A probe that, while it is asked, takes the roster lock as another request would."""

    def __init__(self, engine: AsyncEngine) -> None:
        super().__init__()
        self._engine = engine
        self.took_it = False

    @override
    async def ask(self, request: Request) -> tuple[int, str] | Silence:
        async with asyncio.timeout(WAIT_S), async_sessionmaker(self._engine)() as other:
            async with other.begin():
                await RosterLock(other).take()
            self.took_it = True
        return 200, TOOL


async def test_a_check_holds_no_roster_lock_while_the_model_is_asked(
    engine: AsyncEngine, prefix: str
) -> None:
    probe = LockTakingProbe(engine)
    agents = service(engine, probe)
    (name,) = await agents_on_one_server(agents, prefix, 1)
    async with asyncio.timeout(2 * WAIT_S):
        await agents.check_model(name)
    assert probe.took_it


class LockProbingGuard(Unfrozen):
    """A rename guard that tries the roster lock from another connection while it answers."""

    def __init__(self, engine: AsyncEngine, claimed: set[str]) -> None:
        self._engine, self._claimed = engine, claimed
        self.lock_was_free: bool | None = None

    async def holds(self, name: str) -> list[str]:
        async with async_sessionmaker(self._engine)() as other, other.begin():
            self.lock_was_free = bool(
                await other.scalar(select(func.pg_try_advisory_xact_lock(lock_key("agents"))))
            )
        return [f"holds a claim on {name}"] if name in self._claimed else []


async def test_a_rename_is_checked_while_the_roster_lock_is_held(
    engine: AsyncEngine, prefix: str
) -> None:
    agents = service(engine)
    await agents.add_agent(AgentChange(name=f"{prefix}-a"))
    guard = LockProbingGuard(engine, set())
    agents.register_rename_guard(guard)
    async with asyncio.timeout(2 * WAIT_S):
        done = await agents.edit_agent(f"{prefix}-a", AgentChange(name=f"{prefix}-b"))
    assert done.notice == f"Saved {prefix}-b"
    assert guard.lock_was_free is False


async def test_a_claim_taken_before_the_write_refuses_the_rename_and_changes_nothing(
    engine: AsyncEngine, prefix: str
) -> None:
    agents = service(engine)
    await agents.add_agent(AgentChange(name=f"{prefix}-a"))
    claimed = {f"{prefix}-a"}
    agents.register_rename_guard(LockProbingGuard(engine, claimed))
    with pytest.raises(ConflictError):
        await agents.edit_agent(f"{prefix}-a", AgentChange(name=f"{prefix}-b"))
    assert [a.name for a in await agents.agents() if a.name.startswith(prefix)] == [f"{prefix}-a"]
