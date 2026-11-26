"""`code-factory team leases|release`: the claims on tickets and freeing a stuck one."""

import argparse

import pytest

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.platform.services import Services
from code_factory.team.cli import team_command
from code_factory.team.service import TeamService
from code_factory.tickets.models import Ticket
from team_fakes import FakeClock, Fakes
from team_values import NOW, agent, ended, run


def parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="team")
    team_command.configure(parser)
    return parser.parse_args(argv)


async def run_command(team: TeamService, *argv: str) -> int:
    services = Services()
    services.add(TeamService, team)
    run_async = team_command.run_async
    assert run_async is not None
    return await run_async(parse(*argv), services)


async def test_leases_lists_each_claim_with_its_holder_runs_times_and_whether_it_holds(
    team: TeamService,
    fakes: Fakes,
    clock: FakeClock,
    ticket: Ticket,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fakes.agents.agents = [agent("writer", "spec")]
    await team.claim_for_run(ticket.id, "spec")
    await team.attach_run(ticket.id, "r1")
    fakes.runs.runs = [ended("r1", ticket.id, "writer")]
    clock.now = NOW + 90
    assert await run_command(team, "leases") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["TICKET", "HOLDER", "RUNS", "CLAIMED", "BEAT", "HOLDS"]
    assert lines[1] == (f"{ticket.id}  writer  r1  2026-11-23 12:00:00  2026-11-23 12:00:00  no")


async def test_a_claim_of_the_default_agent_without_runs_is_listed_as_holding(
    team: TeamService, ticket: Ticket, capsys: pytest.CaptureFixture[str]
) -> None:
    await team.claim_for_run(ticket.id, "build")
    await run_command(team, "leases")
    assert capsys.readouterr().out.splitlines()[1] == (
        f"{ticket.id}  the default agent  -  2026-11-23 12:00:00  2026-11-23 12:00:00  yes"
    )


async def test_release_refuses_while_a_run_of_the_claim_is_active(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    await team.claim_for_run(ticket.id, "build")
    await team.attach_run(ticket.id, "r5")
    fakes.runs.runs = [run("r5", ticket.id)]
    with pytest.raises(ConflictError, match=rf"^{ticket.id} has run r5 still running"):
        await run_command(team, "release", ticket.id)
    assert len(await team.list_claims()) == 1


async def test_release_frees_a_stale_claim_and_says_so(
    team: TeamService, ticket: Ticket, clock: FakeClock, capsys: pytest.CaptureFixture[str]
) -> None:
    await team.claim_for_run(ticket.id, "build")
    clock.now = NOW + 600
    assert await run_command(team, "release", ticket.id) == 0
    assert capsys.readouterr().out == f"released the claim on {ticket.id}\n"
    assert await team.list_claims() == []


async def test_release_of_a_ticket_without_a_claim_is_not_found(
    team: TeamService, ticket: Ticket
) -> None:
    with pytest.raises(NotFoundError, match=rf"^{ticket.id} has no claim$"):
        await run_command(team, "release", ticket.id)


async def test_release_needs_a_ticket(team: TeamService) -> None:
    with pytest.raises(BadRequestError, match=r"^release needs a ticket"):
        await run_command(team, "release")
