"""The Team page read through the service: ports read together, git facts, failures."""

import pytest

from code_factory.platform.errors import UnavailableError
from code_factory.team.models import (
    ActiveRun,
    AtWork,
    LandJob,
    RepositoryRef,
    RunningGate,
)
from code_factory.team.service import TeamPorts, TeamService
from team_fakes import FakeClock, FakeGit, Fakes
from team_page_values import activity, owner, ticket
from team_values import NOW, run

DAY = 86_400.0
TODAY = 1_795_392_000.0  # 00:00 UTC of the day NOW falls in


def with_git(base: TeamService, git: FakeGit) -> TeamService:
    """The service of `base` reading git through `git`."""
    return TeamService(base._uow, base._ports_factory, clock=base._clock, git=git)


async def test_every_port_feeds_the_page(team: TeamService, fakes: Fakes) -> None:
    fakes.agents.agents = []
    fakes.tickets.facts = [
        ticket("CF-1", "build", activities=(activity(NOW - 600, "created"),)),
        ticket("CF-2", "build"),
        ticket("CF-3", "build"),
        ticket("CF-4", "build"),
        ticket("CF-5", "spec"),
    ]
    fakes.runs.runs = [run("r1", "CF-1", "builder", started=NOW - 300, repository="sample")]
    fakes.runs.alive = {"r1"}
    fakes.gates.gates = [
        RunningGate(
            repository="sample",
            ticket_id="CF-2",
            tree="/t/CF-2",
            started_at=NOW - 200,
            written_at=NOW - 5,
            log="gate: preflight starts\n",
        )
    ]
    fakes.sessions.at_work = [
        AtWork(
            agent_id="a1",
            ticket_id="CF-3",
            kind="session",
            name="ticket-worker 54f2",
            doing="Edit a.rs",
            since=NOW - 100,
            last_event_at=NOW - 3,
        )
    ]
    fakes.jobs.jobs = [LandJob(ticket_id="CF-4", started_at=NOW - 50, alive=True)]
    fakes.owner.items = [owner("CF-5", "questions", "", NOW - 900, count=2)]
    page = await team.now()
    shown = {
        row.ticket.id if row.ticket else "": (row.state, row.actor.name, row.line)
        for row in page.groups.working
    }
    assert shown == {
        "CF-1": ("working", "builder", "build run"),
        "CF-2": ("working", "gate", "preflight"),
        "CF-3": ("working", "ticket-worker 54f2", "Edit a.rs"),
        "CF-4": ("working", "board land", "landing"),
    }
    assert [(r.line, r.since) for r in page.groups.needs_you] == [("2 open questions", NOW - 900)]
    assert (page.now, page.today) == (NOW, TODAY)


async def test_the_agents_split_into_idle_and_paused_by_the_agents_port(
    team: TeamService, fakes: Fakes
) -> None:
    from team_values import agent  # noqa: PLC0415

    fakes.agents.agents = [
        agent("builder", "build"),
        agent("writer", "spec"),
        agent("muse", "spec", paused_at=NOW - 60),
    ]
    fakes.tickets.facts = [ticket("CF-1", "build")]
    fakes.runs.runs = [run("r1", "CF-1", "builder", repository="sample")]
    fakes.runs.alive = {"r1"}
    page = await team.now()
    assert (page.idle, page.paused) == (("writer",), ("muse",))


async def test_a_run_whose_process_is_gone_is_a_stale_row(team: TeamService, fakes: Fakes) -> None:
    fakes.tickets.facts = [ticket("CF-1", "build")]
    fakes.runs.runs = [run("r1", "CF-1", "builder", started=NOW - 300, repository="sample")]
    page = await team.now()
    assert [(r.state, r.line) for r in page.groups.stale] == [
        ("stale", "build run; its process has ended")
    ]


async def test_without_git_the_cycle_is_the_last_seven_days_and_tickets_have_no_first_commit(
    team: TeamService, fakes: Fakes
) -> None:
    fakes.tickets.facts = [ticket("CF-1", "build")]
    fakes.runs.runs = [run("r1", "CF-1", "builder", repository="sample")]
    fakes.runs.alive = {"r1"}
    page = await team.now()
    assert (page.cycle.since, page.cycle.from_) == (NOW - 7 * DAY, "the last 7 days")
    assert fakes.tickets.since == NOW - 7 * DAY
    assert [m.at for m in page.peek["sample/CF-1"].milestones] == [None] * 5


async def test_git_gives_the_cycle_and_each_tickets_first_commit(
    team: TeamService, fakes: Fakes
) -> None:
    git = FakeGit(
        tags=[("v1.0", NOW - 5 * DAY), ("v1.1", NOW - 2 * DAY), ("nightly", NOW - 1)],
        logs={"/repos/sample": f"{NOW - 4000:.0f}\tCF-1: first\n{NOW - 9000:.0f}\tCF-1: earlier\n"},
    )
    fakes.tickets.repository_list = [RepositoryRef(name="sample", path="/repos/sample")]
    fakes.tickets.facts = [ticket("CF-1", "build")]
    fakes.runs.runs = [run("r1", "CF-1", "builder", repository="sample")]
    fakes.runs.alive = {"r1"}
    page = await with_git(team, git).now()
    assert (page.cycle.since, page.cycle.from_) == (NOW - 2 * DAY, "since v1.1")
    assert fakes.tickets.since == NOW - 2 * DAY  # a cycle older than today reaches back that far
    assert page.peek["sample/CF-1"].milestones[1].at == NOW - 9000
    assert git.reads == ["tags /repos/sample", f"log /repos/sample {NOW - 2 * DAY - 30 * DAY:.0f}"]


async def test_a_cycle_that_began_today_still_reads_the_tickets_merged_since_midnight(
    team: TeamService, fakes: Fakes
) -> None:
    git = FakeGit(tags=[("v2.0", NOW - 60)])
    fakes.tickets.repository_list = [RepositoryRef(name="sample", path="/repos/sample")]
    await with_git(team, git).now()
    assert fakes.tickets.since == TODAY


@pytest.mark.parametrize(
    "port", ["agents", "tickets", "runs", "gates", "owner", "sessions", "jobs"]
)
async def test_a_port_that_fails_fails_the_page_naming_it_never_a_partial_page(
    team: TeamService, fakes: Fakes, port: str
) -> None:
    names = {
        "agents": "the agents",
        "tickets": "the repositories",
        "runs": "the runs",
        "gates": "the gates",
        "owner": "the inbox",
        "sessions": "the sessions",
        "jobs": "the jobs",
    }
    methods = {
        "agents": "team_agents",
        "tickets": "repositories",
        "runs": "active_runs",
        "gates": "running_gates",
        "owner": "owner_items",
        "sessions": "subagents_at_work",
        "jobs": "running_land_jobs",
    }

    async def broken(*_args: object) -> list[object]:
        msg = "the source is down"
        raise RuntimeError(msg)

    setattr(getattr(fakes, port), methods[port], broken)
    with pytest.raises(UnavailableError) as failed:
        await team.now()
    assert str(failed.value) == f"the team page could not read {names[port]}"


async def test_the_tickets_that_cannot_be_read_fail_the_page_too(
    team: TeamService, fakes: Fakes
) -> None:
    async def broken(_since: float) -> list[object]:
        msg = "down"
        raise RuntimeError(msg)

    fakes.tickets.team_facts = broken  # ty: ignore[invalid-assignment]
    with pytest.raises(UnavailableError, match=r"^the team page could not read the tickets$"):
        await team.now()


async def test_a_port_nobody_registered_is_one_sentence_naming_what_is_missing(
    uow: object, clock: FakeClock
) -> None:
    def missing() -> TeamPorts:
        msg = "no service is registered for AgentSource; list its module in app.MODULES"
        raise LookupError(msg)

    service = TeamService(uow, missing, clock=clock)  # ty: ignore[invalid-argument-type]
    with pytest.raises(
        UnavailableError, match=r"^the team cannot reach its sources: no service is"
    ):
        await service.now()


async def test_an_active_run_alone_is_a_row_of_the_runs_ticket(
    team: TeamService, fakes: Fakes
) -> None:
    fakes.tickets.facts = [ticket("CF-1", "build")]
    fakes.runs.runs = [run("r9", "CF-1", "", stage="review", repository="sample")]
    fakes.runs.alive = {"r9"}
    assert ActiveRun(run=fakes.runs.runs[0], alive=True)
    page = await team.now()
    [row] = page.groups.working
    assert (row.actor.kind, row.actor.name, row.line) == ("reviewer", "default", "review run")
