"""A rename and a claim that reads the roster before it writes its lease never interleave."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest

from agents_support import agents_fixture, clock_fixture, store_fixture  # noqa: F401
from code_factory.agents.models.agents import AgentChange
from code_factory.agents.service import AgentService
from code_factory.platform.errors import ConflictError


class Claimer:
    """The claims module's side: one lock held across its read of the roster and its lease."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.leases: set[str] = set()
        self.asked = asyncio.Event()

    @asynccontextmanager
    async def frozen(self, _name: str) -> AsyncGenerator[None]:
        async with self.lock:
            yield

    async def holds(self, name: str) -> list[str]:
        self.asked.set()
        return [f"holds a claim on {name}"] if name in self.leases else []


async def test_a_claim_in_flight_finishes_before_the_rename_asks_and_then_refuses_it(
    agents: AgentService,
) -> None:
    claimer = Claimer()
    agents.register_rename_guard(claimer)
    await agents.add_agent(AgentChange(name="a"))
    read_the_roster, release = asyncio.Event(), asyncio.Event()

    async def claim() -> None:
        async with claimer.lock:
            assert [a.name for a in await agents.agents()] == ["a"]
            read_the_roster.set()
            await release.wait()
            claimer.leases.add("a")

    claiming = asyncio.create_task(claim())
    await read_the_roster.wait()
    renaming = asyncio.create_task(agents.edit_agent("a", AgentChange(name="b")))
    asked = claimer.asked.wait()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asked, 1)
    release.set()
    await claiming
    with pytest.raises(ConflictError):
        await renaming
    assert [a.name for a in await agents.agents()] == ["a"]
