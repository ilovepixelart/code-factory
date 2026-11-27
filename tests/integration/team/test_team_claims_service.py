"""Claims through the service, on Postgres: claim and pick together, the holder checks, the keeper.

Expected values: the team spec's hand-worked cases and the previous implementation's claim tests
(`a_held_claim_refuses_a_second_one`, `a_claim_beats_while_its_run_runs_and_ends_with_it`,
`a_claim_without_a_heartbeat_for_60_seconds_is_reclaimed`).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import pytest

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.platform.services import Services
from code_factory.runs.ports import Settings
from code_factory.runs.service.neighbours import TeamsAdapter
from code_factory.team.models import TicketAsk
from code_factory.team.service import TeamService
from code_factory.tickets.models import Ticket
from team_fakes import FakeClock, Fakes
from team_values import NOW, agent, ended, run


async def test_a_claim_names_the_agent_the_pick_took_and_the_holder_reads_it(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.agents.agents = [agent("writer", "spec"), agent("coder", "build")]
    claim = await team.claim_for_run(ticket.id, "spec")
    assert claim.agent is not None
    assert (claim.agent.name, claim.passed_over) == ("writer", ())
    assert await team.holder(ticket.id) == "writer"
    assert await team.busy() == {"writer": ticket.id}
    [view] = await team.list_claims()
    assert (view.ticket_id, view.agent, view.runs, view.claimed_at, view.holds) == (
        ticket.id,
        "writer",
        (),
        NOW,
        True,
    )


async def test_with_no_agent_defined_the_default_agent_holds_the_claim_and_has_no_holder_name(
    team: TeamService, ticket: Ticket
) -> None:
    claim = await team.claim_for_run(ticket.id, "build")
    assert claim.agent is None
    assert await team.holder(ticket.id) is None
    assert await team.busy() == {}
    assert [view.agent for view in await team.list_claims()] == [""]


async def test_a_held_claim_refuses_a_second_naming_its_holder(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.agents.agents = [agent("writer", "spec"), agent("scribe", "spec")]
    await team.claim_for_run(ticket.id, "spec")
    with pytest.raises(ConflictError, match=r"^writer holds this ticket$"):
        await team.claim_for_run(ticket.id, "spec")
    assert [view.agent for view in await team.list_claims()] == ["writer"]


async def test_the_default_agents_claim_is_named_the_default_agent(
    team: TeamService, ticket: Ticket
) -> None:
    await team.claim_for_run(ticket.id, "build")
    with pytest.raises(ConflictError, match=r"^the default agent holds this ticket$"):
        await team.claim_for_run(ticket.id, "build")


async def test_a_refusal_leaves_no_claim_row(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.agents.agents = [agent("coder", "build", types=("bug",))]
    with pytest.raises(
        ConflictError,
        match=r"^no agent of this column takes this ticket's type and labels$",
    ):
        await team.claim_for_run(ticket.id, "build")
    assert await team.list_claims() == []


async def test_one_free_agent_goes_to_one_ticket_and_the_next_waits_on_it(
    team: TeamService, fakes: Fakes, more_tickets: Callable[[int], Awaitable[list[Ticket]]]
) -> None:
    first, second = await more_tickets(2)
    fakes.agents.agents = [agent("writer", "spec")]
    await team.claim_for_run(first.id, "spec")
    with pytest.raises(ConflictError, match=rf"^writer working {first.id}$"):
        await team.claim_for_run(second.id, "spec")


async def test_the_agents_passed_over_are_named_with_why(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.agents.agents = [
        agent("first", "build", refusal="first is broken"),
        agent("second", "build"),
    ]
    claim = await team.claim_for_run(ticket.id, "build")
    assert claim.agent is not None
    assert (claim.agent.name, claim.passed_over) == ("second", ("first is broken",))


async def test_a_run_of_the_ticket_is_read_so_a_reviewer_never_writes_its_own_build(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.agents.agents = [agent("rev", "review")]
    fakes.runs.runs = [ended("r1", ticket.id, "rev", stage="build")]
    with pytest.raises(ConflictError, match=r"^no reviewer that did not write the code$"):
        await team.claim_for_run(ticket.id, "review")


async def test_the_ticket_type_and_labels_come_from_the_tickets_port(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.tickets.asks = {ticket.id: TicketAsk(kind="bug", labels="web, api", repository="sample")}
    fakes.agents.agents = [
        agent("a", "build", types=("feature",)),
        agent("b", "build", labels=("api",)),
    ]
    claim = await team.claim_for_run(ticket.id, "build")
    assert claim.agent is not None
    assert claim.agent.name == "b"


async def test_an_unknown_ticket_is_not_found_and_a_bad_id_is_refused(
    team: TeamService, fakes: Fakes
) -> None:
    fakes.tickets.asks = {}
    with pytest.raises(NotFoundError, match=r"^CF-999999999 does not exist$"):
        await team.claim_for_run("CF-999999999", "build")
    with pytest.raises(BadRequestError, match=r"is not a ticket id CF-<n>"):
        await team.claim_for_run("999", "build")


async def test_a_run_attached_under_the_claim_keeps_it_while_the_run_is_active(
    team: TeamService, fakes: Fakes, clock: FakeClock, ticket: Ticket
) -> None:
    await team.claim_for_run(ticket.id, "build")
    await team.attach_run(ticket.id, "r1")
    fakes.runs.runs = [run("r1", ticket.id)]
    clock.now = NOW + 3600
    [view] = await team.list_claims()
    assert (view.runs, view.holds) == (("r1",), True)
    fakes.runs.runs = [ended("r1", ticket.id)]
    [view] = await team.list_claims()
    assert view.holds is False


async def test_a_claim_naming_a_run_that_is_not_recorded_holds_while_its_beat_is_fresh(
    team: TeamService, clock: FakeClock, ticket: Ticket
) -> None:
    await team.claim_for_run(ticket.id, "build")
    await team.attach_run(ticket.id, "lost-run")
    clock.now = NOW + 59
    assert [v.holds for v in await team.list_claims()] == [True]
    clock.now = NOW + 60
    assert [v.holds for v in await team.list_claims()] == [False]


async def test_attaching_a_run_to_a_ticket_without_a_claim_is_not_found(
    team: TeamService, ticket: Ticket
) -> None:
    with pytest.raises(NotFoundError, match=rf"^{ticket.id} has no claim to record run r1 under"):
        await team.attach_run(ticket.id, "r1")


async def test_ending_a_claim_deletes_it_and_a_second_end_is_not_found(
    team: TeamService, ticket: Ticket
) -> None:
    await team.claim_for_run(ticket.id, "build")
    await team.end_claim(ticket.id)
    assert await team.list_claims() == []
    with pytest.raises(NotFoundError, match=rf"^{ticket.id} has no claim$"):
        await team.end_claim(ticket.id)


async def test_a_runner_claims_beats_and_releases_only_its_own_claim(
    team: TeamService, clock: FakeClock, ticket: Ticket
) -> None:
    assert await team.claim(ticket.id, "runner:a") is True
    assert await team.claim(ticket.id, "runner:b") is False
    assert await team.beat(ticket.id, "runner:b") is False
    clock.now = NOW + 30
    assert await team.beat(ticket.id, "runner:a") is True
    assert (await team.list_claims())[0].beat_at == NOW + 30
    assert await team.release(ticket.id, "runner:b") is False
    assert await team.release(ticket.id, "runner:a") is True
    assert await team.list_claims() == []
    assert await team.release(ticket.id, "runner:a") is False


async def test_a_lapsed_runner_claim_cannot_be_beaten_or_released_and_is_taken_over(
    team: TeamService, clock: FakeClock, ticket: Ticket
) -> None:
    await team.claim(ticket.id, "runner:a")
    clock.now = NOW + 60
    assert await team.beat(ticket.id, "runner:a") is False
    assert await team.release(ticket.id, "runner:a") is False
    assert await team.claim(ticket.id, "runner:b") is True
    assert [v.agent for v in await team.list_claims()] == ["runner:b"]


async def test_the_keeper_beats_a_claim_with_an_active_run_and_deletes_ended_and_stale_ones(
    team: TeamService,
    fakes: Fakes,
    clock: FakeClock,
    more_tickets: Callable[[int], Awaitable[list[Ticket]]],
) -> None:
    one, two, three = await more_tickets(3)
    for item in (one, two, three):
        await team.claim_for_run(item.id, "build")
    await team.attach_run(one.id, "r1")
    await team.attach_run(two.id, "r2")
    fakes.runs.runs = [run("r1", one.id), ended("r2", two.id)]
    clock.now = NOW + 90
    assert await team.keep() == 2
    [view] = await team.list_claims()
    assert (view.ticket_id, view.claimed_at, view.beat_at) == (one.id, NOW, NOW + 90)
    assert await team.keep() == 0


async def test_the_keeper_loop_survives_a_failed_pass_logs_it_and_stops_on_cancellation(
    team: TeamService,
    fakes: Fakes,
    ticket: Ticket,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await team.claim_for_run(ticket.id, "build")
    await team.attach_run(ticket.id, "r1")
    fakes.runs.failing = True
    fakes.runs.runs = [run("r1", ticket.id)]
    with caplog.at_level(logging.ERROR, logger="code_factory.team.service.claims"):
        keeper = asyncio.create_task(team.run_keeper(interval=0.01))
        async with asyncio.timeout(15):
            while "the team keeper pass failed" not in caplog.text:  # noqa: ASYNC110
                await asyncio.sleep(0.01)
        assert not keeper.done()
        keeper.cancel()
        with pytest.raises(asyncio.CancelledError):
            await keeper
    assert "the team keeper pass failed" in caplog.text
    assert "the runs table is gone" in caplog.text


async def test_start_refusal_is_the_sentence_a_start_would_meet_and_writes_nothing(
    team: TeamService, fakes: Fakes, clock: FakeClock, ticket: Ticket
) -> None:
    fakes.agents.agents = [agent("writer", "spec")]
    assert await team.start_refusal(ticket.id, "spec") is None
    assert await team.list_claims() == []
    await team.claim_for_run(ticket.id, "spec")
    assert await team.start_refusal(ticket.id, "spec") == "writer holds this ticket"
    clock.now = NOW + 60
    assert await team.start_refusal(ticket.id, "spec") is None


async def test_start_refusal_says_no_agent_takes_the_ticket(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.agents.agents = [agent("coder", "build", types=("bug",))]
    assert await team.start_refusal(ticket.id, "build") == (
        "no agent of this column takes this ticket's type and labels"
    )


async def test_a_stale_claim_reports_no_holder_and_holders_lists_only_defined_agents(
    team: TeamService,
    fakes: Fakes,
    clock: FakeClock,
    more_tickets: Callable[[int], Awaitable[list[Ticket]]],
) -> None:
    named, unnamed = await more_tickets(2)
    fakes.agents.agents = [agent("writer", "spec")]
    await team.claim_for_run(named.id, "spec")
    fakes.agents.agents = []
    await team.claim_for_run(unnamed.id, "build")
    assert await team.holders([named.id, unnamed.id]) == {named.id: "writer"}
    clock.now = NOW + 61
    assert await team.holders([named.id, unnamed.id]) == {}
    assert await team.busy() == {}


async def test_force_release_refuses_while_a_run_is_active_and_frees_a_stuck_claim(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    await team.claim_for_run(ticket.id, "build")
    await team.attach_run(ticket.id, "r7")
    fakes.runs.runs = [run("r7", ticket.id)]
    with pytest.raises(
        ConflictError, match=rf"^{ticket.id} has run r7 still running; stop the run first$"
    ):
        await team.force_release(ticket.id)
    fakes.runs.runs = [ended("r7", ticket.id)]
    await team.force_release(ticket.id)
    assert await team.list_claims() == []


async def test_force_release_of_a_ticket_without_a_claim_is_not_found(
    team: TeamService, ticket: Ticket
) -> None:
    with pytest.raises(NotFoundError, match=rf"^{ticket.id} has no claim$"):
        await team.force_release(ticket.id)


async def test_the_flags_of_a_start_reach_the_pick(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    coder = agent("coder", "build", runtime="claude", model="m")
    same = agent("same", "review", runtime="claude", model="m")
    fakes.agents.agents = [coder, same]
    fakes.runs.runs = [ended("r1", ticket.id, "coder", stage="build")]
    with pytest.raises(ConflictError, match=r"^no reviewer on another model than the code's$"):
        await team.claim_for_run(ticket.id, "review", other_model=True)
    assert await team.start_refusal(ticket.id, "review", other_model=True) == (
        "no reviewer on another model than the code's"
    )
    assert await team.start_refusal(ticket.id, "review") is None


async def test_escalation_passes_the_agent_that_failed_the_stage(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.agents.agents = [agent("first", "build"), agent("second", "build")]
    fakes.runs.runs = [ended("r1", ticket.id, "first", exit_code=1)]
    claim = await team.claim_for_run(ticket.id, "build", escalate=True)
    assert claim.agent is not None
    assert claim.agent.name == "second"
    assert claim.passed_over == ("first failed this ticket at Build (exit 1)",)


async def test_a_runner_claim_on_a_ticket_that_does_not_exist_is_not_found(
    team: TeamService,
) -> None:
    with pytest.raises(NotFoundError, match=r"^CF-999999999 does not exist"):
        await team.claim("CF-999999999", "runner:a")


async def test_a_claim_reads_the_live_tokens_of_the_tickets_runs_for_the_cap(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.agents.agents = [agent("builder", "build", max_tokens=100)]
    fakes.runs.runs = [ended("r1", ticket.id, "builder", tokens=100)]
    fakes.runs.stale_tokens = None
    with pytest.raises(ConflictError, match=r"^builder 100 of 100 tokens$"):
        await team.claim_for_run(ticket.id, "build")


async def test_ending_a_claim_for_a_run_deletes_only_a_claim_that_run_is_under(
    team: TeamService, ticket: Ticket
) -> None:
    await team.claim_for_run(ticket.id, "build")
    await team.attach_run(ticket.id, "r1")
    with pytest.raises(
        ConflictError, match=rf"^{ticket.id} is claimed again and run r2 is not under"
    ):
        await team.end_claim(ticket.id, run_id="r2")
    assert len(await team.list_claims()) == 1
    await team.end_claim(ticket.id, run_id="r1")
    assert await team.list_claims() == []


async def test_a_run_ending_after_its_claim_was_taken_again_leaves_the_new_claim(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.agents.agents = [agent("first", "build"), agent("second", "build")]
    await team.claim_for_run(ticket.id, "build")
    await team.attach_run(ticket.id, "old-run")
    fakes.runs.runs = [ended("old-run", ticket.id, "first")]
    taken = await team.claim_for_run(ticket.id, "build")
    assert taken.agent is not None
    with pytest.raises(ConflictError):
        await team.end_claim(ticket.id, run_id="old-run")
    assert [view.agent for view in await team.list_claims()] == [taken.agent.name]


async def test_a_starting_claim_can_be_kept_without_beating_its_replacement(
    team: TeamService, fakes: Fakes, ticket: Ticket, clock: FakeClock
) -> None:
    fakes.agents.agents = [agent("writer", "build")]
    services = Services()
    services.add(TeamService, team)
    runs = TeamsAdapter(services)
    held = await runs.claim_for_run(ticket.id, "build", Settings())
    assert held.lease_id is not None
    clock.now += 55
    assert await runs.beat_start(ticket.id, held.lease_id)
    clock.now += 55
    assert await team.keep() == 0
    clock.now += 5
    assert not await team.beat_start(ticket.id, held.lease_id)

    await team.force_release(ticket.id)
    replacement = await team.claim_for_run(ticket.id, "build")
    assert replacement.lease_id != held.lease_id
    assert not await team.beat_start(ticket.id, held.lease_id)
    with pytest.raises(ConflictError, match="the ticket's starting claim changed"):
        await team.attach_run(ticket.id, "late", lease_id=held.lease_id)
    with pytest.raises(ConflictError, match="the ticket's starting claim changed"):
        await team.end_claim(ticket.id, lease_id=held.lease_id)
    await runs.attach_run(ticket.id, "actual", lease_id=replacement.lease_id)
    [kept] = await team.list_claims()
    assert kept.runs == ("actual",)
