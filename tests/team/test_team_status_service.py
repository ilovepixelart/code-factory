"""What agents do, their lanes and caps, and the queue's rule, read through the service."""

from code_factory.team.models import Doing, OpenChange, TicketFacts, TicketRef
from code_factory.team.service import TeamService
from code_factory.tickets.models import Ticket
from team_fakes import Fakes
from team_values import DAY, NOW, agent, ended, run

HOUR = 3600.0


async def test_an_agent_holding_a_claim_with_a_running_run_is_working_on_that_ticket(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.agents.agents = [agent("builder", "build"), agent("idle", "spec")]
    await team.claim_for_run(ticket.id, "build")
    await team.attach_run(ticket.id, "r1")
    fakes.runs.runs = [
        run("r1", ticket.id, "builder", started=NOW - 100, repository="sample", tokens=40)
    ]
    found = await team.doing()
    assert list(found) == ["builder"]
    state = found["builder"]
    assert (state.state, state.repository, state.id) == ("working", "sample", ticket.id)
    assert state.usage is not None
    assert (state.usage.tokens, state.usage.seconds) == (40, 100)


async def test_an_agent_at_a_cap_without_a_claim_is_over_limit_on_its_last_ticket(
    team: TeamService, fakes: Fakes
) -> None:
    fakes.agents.agents = [agent("builder", "build", max_tokens=100)]
    fakes.runs.runs = [ended("r1", "CF-9", "builder", tokens=100, repository="api")]
    assert await team.doing() == {
        "builder": Doing(state="over limit", repository="api", id="CF-9", usage=None)
    }


async def test_last_says_how_each_agents_latest_run_ended(team: TeamService, fakes: Fakes) -> None:
    fakes.agents.agents = [agent("builder", "build"), agent("idle", "spec")]
    fakes.runs.runs = [
        ended("old", "CF-1", "builder", started=NOW - 900, repository="api"),
        ended(
            "new", "CF-2", "builder", started=NOW - 500, seconds=30, exit_code=1, repository="api"
        ),
    ]
    found = await team.last()
    assert list(found) == ["builder"]
    assert (found["builder"].run, found["builder"].id, found["builder"].outcome) == (
        "new",
        "CF-2",
        "failed",
    )
    assert found["builder"].at == NOW - 470


async def test_lanes_hold_the_runs_of_the_last_six_hours_and_the_still_running_ones(
    team: TeamService, fakes: Fakes
) -> None:
    fakes.agents.agents = [agent("builder", "build")]
    fakes.runs.runs = [
        ended("too-old", "CF-1", "builder", started=NOW - 8 * HOUR, seconds=HOUR, repository="api"),
        run("long", "CF-2", "builder", started=NOW - 8 * HOUR, repository="api"),
        ended("recent", "CF-1", "builder", started=NOW - 2 * HOUR, seconds=600, repository="api"),
        ended("nobody", "CF-3", "", started=NOW - HOUR, repository="api"),
    ]
    result = await team.lanes()
    assert (result.since, result.now) == (NOW - 6 * HOUR, NOW)
    assert [(lane.agent, [r.id for r in lane.runs]) for lane in result.lanes] == [
        ("builder", ["long", "recent"]),
        ("default", ["nobody"]),
    ]
    assert [(c.ticket, c.runs) for c in result.chains] == [
        ("CF-2", ("long",)),
        ("CF-1", ("recent",)),
        ("CF-3", ("nobody",)),
    ]


async def test_over_cap_names_the_cap_a_running_run_reached_or_nothing(
    team: TeamService, fakes: Fakes
) -> None:
    fakes.agents.agents = [agent("builder", "build", max_tokens=100, max_daily_usd=1.0)]
    fakes.runs.runs = [run("r1", "CF-1", "builder", tokens=100)]
    assert await team.over_cap("builder", "CF-1") == "builder 100 of 100 tokens"
    assert await team.over_cap("builder", "CF-2") is None
    assert await team.over_cap("stranger", "CF-1") is None
    fakes.runs.runs = [ended("r2", "CF-7", "builder", cost=1.0)]
    assert await team.over_cap("builder", "CF-1") == "builder $1.00 of $1.00 on 2026-11-23"


async def test_the_queue_rule_reads_the_runs_of_the_cards_it_plans(
    team: TeamService, fakes: Fakes
) -> None:
    fakes.agents.agents = [agent("rev", "review"), agent("writer", "spec")]
    fakes.runs.runs = [ended("r1", "CF-5", "rev", stage="build")]
    planned = await team.queue_rule(["CF-5", "CF-6"])
    assert planned("CF-5", "review", "feature", "") == "no reviewer that did not write the code"
    assert planned("CF-6", "review", "feature", "") == ""
    assert planned.parked is True


async def test_the_queue_rule_without_ids_knows_who_wrote_the_open_tickets_older_runs(
    team: TeamService, fakes: Fakes
) -> None:
    fakes.agents.agents = [agent("rev", "review")]
    fakes.tickets.facts = [
        TicketFacts(
            reference=TicketRef(repository="sample", id="CF-5", title="five"),
            kind="feature",
            column="Review",
        )
    ]
    fakes.runs.runs = [
        ended("r1", "CF-5", "rev", started=NOW - 3 * DAY, stage="build"),
        ended("r2", "CF-9", "rev", started=NOW - 600, stage="build"),
    ]
    planned = await team.queue_rule()
    assert planned("CF-5", "review", "feature", "") == "no reviewer that did not write the code"


async def test_the_queue_rule_knows_the_agents_busy_through_claims(
    team: TeamService, fakes: Fakes, ticket: Ticket
) -> None:
    fakes.agents.agents = [agent("writer", "spec")]
    await team.claim_for_run(ticket.id, "spec")
    planned = await team.queue_rule()
    assert planned("CF-999999", "spec", "feature", "") == f"writer working {ticket.id}"


async def test_the_pass_throughs_are_the_rules_words(team: TeamService) -> None:
    assert team.hold_summary("spec", "x", ("requirements", "uat")) == "requirements and UAT"
    assert team.queue_note("likely overlaps #1 in a", "") == "next, likely overlaps #1 in a"
    changes = [
        OpenChange(ticket_id="CF-1", label="#1", files=("src/a/x.py",)),
        OpenChange(ticket_id="CF-2", label="#2", files=("src/a/y.py",)),
    ]
    assert team.overlap_note("touch src/a", "CF-1", changes) == "likely overlaps #2 in src/a/y.py"
    assert team.overlap_note("touch src/a", "CF-3", changes) == "likely overlaps #1 in src/a/x.py"
    assert team.subagent_ticket(["cd /r/.w/CF-4/x"], "/.worktrees/") is None
    assert team.subagent_ticket(["cd /r/.w/CF-4/x"], ".w/") == "CF-4"


async def test_the_ticket_runs_with_live_tokens_win_over_the_same_run_read_elsewhere(
    team: TeamService, fakes: Fakes
) -> None:
    fakes.agents.agents = [agent("builder", "build", max_tokens=100)]
    fakes.runs.runs = [run("r1", "CF-1", "builder", tokens=100)]
    fakes.runs.stale_tokens = None
    assert await team.over_cap("builder", "CF-1") == "builder 100 of 100 tokens"
    window = await team.lanes()
    [lane] = window.lanes
    assert [(r.id, r.outcome) for r in lane.runs] == [("r1", "running")]
    state = (await team.doing())["builder"]
    assert (state.state, state.id) == ("over limit", "CF-1")
