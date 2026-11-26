"""Claim and pick under real concurrency: separate committed sessions, since the savepoint
fixture of the other tests runs everything on one connection and cannot show a race."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable

import pytest
from sqlalchemy import text

from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine, create_session_factory
from code_factory.platform.errors import ConflictError
from code_factory.team.models import Claim
from code_factory.team.service import TeamService
from team_fakes import FakeClock, Fakes
from team_values import agent

Setup = tuple[TeamService, TeamService, Fakes, Callable[[int], Awaitable[list[str]]]]


@pytest.fixture
async def committed(settings: Settings, migrated: None) -> AsyncGenerator[Setup]:  # noqa: ARG001
    """Two services over committed sessions, as two processes would be (each has its own in-process
    lock, so only the database lock orders them), and a factory of committed tickets."""
    engine = create_engine(settings)
    uow = UnitOfWork(create_session_factory(engine))
    fakes = Fakes()
    made: list[int] = []

    async def tickets(count: int) -> list[str]:
        async with uow() as session:
            for _ in range(count):
                row = await session.execute(
                    text(
                        "insert into tickets (repository, title) "
                        "values ('race', 'r') returning number"
                    )
                )
                made.append(row.scalar_one())
        return [f"CF-{number}" for number in made[-count:]]

    try:
        yield (
            TeamService(uow, fakes.ports, clock=FakeClock()),
            TeamService(uow, fakes.ports, clock=FakeClock()),
            fakes,
            tickets,
        )
    finally:
        async with uow() as session:
            await session.execute(
                text("delete from team_leases where ticket_number = any(:made)"), {"made": made}
            )
            await session.execute(
                text("delete from tickets where number = any(:made)"), {"made": made}
            )
        await engine.dispose()


async def test_two_simultaneous_claims_on_one_ticket_give_one_claim_and_one_conflict(
    committed: Setup,
) -> None:
    team, rival, fakes, tickets = committed
    fakes.agents.agents = [agent("writer", "spec"), agent("scribe", "spec")]
    [ticket] = await tickets(1)
    results = await asyncio.gather(
        team.claim_for_run(ticket, "spec"),
        rival.claim_for_run(ticket, "spec"),
        return_exceptions=True,
    )
    claims = [r for r in results if isinstance(r, Claim)]
    refused = [r for r in results if isinstance(r, ConflictError)]
    assert (len(claims), len(refused)) == (1, 1)
    assert str(refused[0]) == "writer holds this ticket"
    assert [view.ticket_id for view in await team.list_claims() if view.ticket_id == ticket] == [
        ticket
    ]


async def test_two_tickets_and_one_free_agent_give_it_to_one_and_make_the_other_wait(
    committed: Setup,
) -> None:
    team, rival, fakes, tickets = committed
    fakes.agents.agents = [agent("writer", "spec")]
    first, second = await tickets(2)
    results = await asyncio.gather(
        team.claim_for_run(first, "spec"),
        rival.claim_for_run(second, "spec"),
        return_exceptions=True,
    )
    claims = [r for r in results if isinstance(r, Claim)]
    refused = [r for r in results if isinstance(r, ConflictError)]
    assert (len(claims), len(refused)) == (1, 1)
    assert str(refused[0]).startswith("writer working CF-")


async def test_two_tickets_and_two_agents_give_each_its_own_agent(committed: Setup) -> None:
    team, rival, fakes, tickets = committed
    fakes.agents.agents = [agent("writer", "spec"), agent("scribe", "spec")]
    first, second = await tickets(2)
    results = await asyncio.gather(
        team.claim_for_run(first, "spec"), rival.claim_for_run(second, "spec")
    )
    names = sorted(r.agent.name for r in results if r.agent is not None)
    assert names == ["scribe", "writer"]
