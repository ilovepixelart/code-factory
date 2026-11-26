"""Claim decisions queue up in the process, not on pooled connections: with a pool of two, a
decision whose own port reads need a second connection still finishes while others wait."""

import asyncio
from collections.abc import AsyncGenerator, Sequence

import pytest
from sqlalchemy import text

from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_session_factory
from code_factory.platform.db.engine import create_engine
from code_factory.team.models import TeamAgent
from code_factory.team.service import TeamService
from team_fakes import FakeClock, Fakes
from team_values import agent


class AgentsReadingTheDatabase:
    """An agents port that, as the real one does, reads through the same pool."""

    def __init__(self, uow: UnitOfWork, agents: Sequence[TeamAgent]) -> None:
        self._uow = uow
        self._agents = list(agents)

    async def team_agents(self) -> list[TeamAgent]:
        async with self._uow() as session:
            await session.execute(text("select 1"))
        return list(self._agents)


@pytest.fixture
async def small_pool(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> AsyncGenerator[tuple[UnitOfWork, list[int]]]:
    """A unit of work over a pool of two connections, and the committed tickets made through it."""
    # The app's engine over a pool of two, so it reads the worker's schema as the app does.
    engine = create_engine(
        settings.model_copy(
            update={"db_pool_size": 2, "db_max_overflow": 0, "db_pool_timeout_s": 3}
        )
    )
    uow = UnitOfWork(create_session_factory(engine))
    made: list[int] = []
    try:
        yield uow, made
    finally:
        async with uow() as session:
            await session.execute(
                text("delete from team_leases where ticket_number = any(:made)"), {"made": made}
            )
            await session.execute(
                text("delete from tickets where number = any(:made)"), {"made": made}
            )
        await engine.dispose()


async def test_concurrent_claims_do_not_use_up_the_pool_their_own_reads_need(
    small_pool: tuple[UnitOfWork, list[int]],
) -> None:
    uow, made = small_pool
    async with uow() as session:
        for _ in range(4):
            row = await session.execute(
                text(
                    "insert into tickets (repository, title) values ('pool', 'p') returning number"
                )
            )
            made.append(row.scalar_one())
    fakes = Fakes()
    fakes.agents = AgentsReadingTheDatabase(  # ty: ignore[invalid-assignment]
        uow, [agent(f"a{n}", "build") for n in range(4)]
    )
    team = TeamService(uow, fakes.ports, clock=FakeClock())
    async with asyncio.timeout(10):
        claims = await asyncio.gather(*(team.claim_for_run(f"CF-{n}", "build") for n in made))
    assert sorted(c.agent.name for c in claims if c.agent) == ["a0", "a1", "a2", "a3"]


async def test_concurrent_start_refusals_do_not_hold_a_connection_while_reading_ports(
    small_pool: tuple[UnitOfWork, list[int]],
) -> None:
    uow, made = small_pool
    async with uow() as session:
        for _ in range(4):
            row = await session.execute(
                text(
                    "insert into tickets (repository, title) values ('pool', 'p') returning number"
                )
            )
            made.append(row.scalar_one())
    fakes = Fakes()
    fakes.agents = AgentsReadingTheDatabase(  # ty: ignore[invalid-assignment]
        uow, [agent(f"a{n}", "build") for n in range(4)]
    )
    team = TeamService(uow, fakes.ports, clock=FakeClock())
    async with asyncio.timeout(10):
        refusals = await asyncio.gather(*(team.start_refusal(f"CF-{n}", "build") for n in made))
    assert refusals == [None, None, None, None]
