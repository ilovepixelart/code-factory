"""The runs a claim decision reads beyond the ticket's own: today's and those under claims."""

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from code_factory.platform.errors import ConflictError
from code_factory.team.service import TeamService
from code_factory.tickets.models import Ticket
from team_fakes import FakeClock, Fakes
from team_values import DAY, NOW, agent, ended, run


async def test_an_agent_at_its_day_cap_through_runs_on_other_tickets_is_passed_over(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.agents.agents = [
        agent("builder", "build", max_daily_usd=1.0),
        agent("spare", "build"),
    ]
    fakes.runs.runs = [
        ended("r1", "CF-7000", "builder", started=NOW - 3000, cost=0.9),
        ended("r2", "CF-7001", "builder", started=NOW - 1000, cost=0.2),
    ]
    claim = await team.claim_for_run(ticket.id, "build")
    assert claim.agent is not None
    assert claim.agent.name == "spare"


async def test_an_agent_under_its_day_cap_is_picked_first(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.agents.agents = [
        agent("builder", "build", max_daily_usd=1.0),
        agent("spare", "build"),
    ]
    fakes.runs.runs = [
        ended("r1", "CF-7000", "builder", started=NOW - DAY, cost=0.9),
        ended("r2", "CF-7001", "builder", started=NOW - 1000, cost=0.2),
    ]
    claim = await team.claim_for_run(ticket.id, "build")
    assert claim.agent is not None
    assert claim.agent.name == "builder"


async def test_a_claim_whose_active_run_is_old_still_keeps_its_agent_busy_after_its_beat_lapsed(
    team: TeamService,
    fakes: Fakes,
    clock: FakeClock,
    more_tickets: Callable[[int], Awaitable[list[Ticket]]],
) -> None:
    first, second = await more_tickets(2)
    fakes.agents.agents = [agent("writer", "spec")]
    await team.claim_for_run(first.id, "spec")
    await team.attach_run(first.id, "r1")
    fakes.runs.runs = [
        run("r1", first.id, "writer", started=NOW - 3 * DAY, stage="spec"),
        ended("r2", "CF-7001", "writer", started=NOW - 1000, stage="spec"),
    ]
    clock.now += 120
    with pytest.raises(ConflictError, match=rf"^writer working {first.id}$"):
        await team.claim_for_run(second.id, "spec")


async def test_a_claim_whose_run_ended_does_not_keep_its_agent_busy_while_its_beat_is_fresh(
    team: TeamService,
    fakes: Fakes,
    more_tickets: Callable[[int], Awaitable[list[Ticket]]],
) -> None:
    first, second = await more_tickets(2)
    fakes.agents.agents = [agent("writer", "spec")]
    await team.claim_for_run(first.id, "spec")
    await team.attach_run(first.id, "r1")
    fakes.runs.runs = [
        ended("r1", first.id, "writer", started=NOW - 3 * DAY, stage="spec"),
        ended("r2", "CF-7001", "writer", started=NOW - 1000, stage="spec"),
    ]
    claim = await team.claim_for_run(second.id, "spec")
    assert claim.agent is not None
    assert claim.agent.name == "writer"


async def test_the_keeper_makes_its_first_pass_one_interval_in(
    team: TeamService, fakes: Fakes, clock: FakeClock, ticket: Ticket
) -> None:
    fakes.agents.agents = [agent("writer", "spec")]
    await team.claim_for_run(ticket.id, "spec")
    clock.now = NOW + 120  # the claim has lapsed: a pass deletes it
    keeper = asyncio.create_task(team.run_keeper(interval=0.4))
    await asyncio.sleep(0.1)
    assert [view.ticket_id for view in await team.list_claims()] == [ticket.id]
    await asyncio.sleep(0.6)  # the pass runs while nothing else uses the connection
    keeper.cancel()
    with pytest.raises(asyncio.CancelledError):
        await keeper
    assert await team.list_claims() == []
