"""Fake ports and a clock for the team service tests; each fake holds what it answers."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import override

from code_factory.platform.errors import NotFoundError
from code_factory.team.adapters import GitFacts
from code_factory.team.models import (
    ActiveRun,
    AtWork,
    LandJob,
    OwnerItem,
    RepositoryRef,
    RunningGate,
    TeamAgent,
    TeamRun,
    TicketAsk,
    TicketFacts,
)
from code_factory.team.service import TeamPorts
from team_values import NOW


class FakeClock:
    """A settable clock in epoch seconds, read as the service reads a `datetime`."""

    def __init__(self, now: float = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return datetime.fromtimestamp(self.now, UTC)


class FakeAgents:
    def __init__(self, agents: Sequence[TeamAgent] = ()) -> None:
        self.agents = list(agents)

    async def team_agents(self) -> list[TeamAgent]:
        return list(self.agents)


class FakeRuns:
    """Answers from `runs`; `failing` makes `runs_by_ids` raise once.

    `stale_tokens` makes every answer but `runs_on_ticket` report these tokens, as sources that
    only read a run's record, not its live log, do.
    """

    def __init__(self, runs: Sequence[TeamRun] = (), alive: Sequence[str] = ()) -> None:
        self.runs = list(runs)
        self.alive = set(alive)
        self.failing = False
        self.stale_tokens: int | bool | None = False

    def _recorded(self, runs: Sequence[TeamRun]) -> list[TeamRun]:
        if self.stale_tokens is False:
            return list(runs)
        return [r.model_copy(update={"tokens": self.stale_tokens}) for r in runs]

    async def runs_on_ticket(self, ticket_id: str) -> list[TeamRun]:
        return [r for r in self.runs if r.ticket_id == ticket_id]

    async def latest_runs(self, agent_names: Sequence[str]) -> list[TeamRun]:
        latest: dict[str, TeamRun] = {}
        for run in sorted(self.runs, key=lambda r: r.started_at):
            if run.agent in agent_names:
                latest[run.agent] = run
        return self._recorded(list(latest.values()))

    async def runs_since(self, moment: float) -> list[TeamRun]:
        return self._recorded([r for r in self.runs if r.started_at >= moment])

    async def runs_by_ids(self, ids: Sequence[str]) -> list[TeamRun]:
        if self.failing:
            self.failing = False
            msg = "the runs table is gone"
            raise RuntimeError(msg)
        return self._recorded([r for r in self.runs if r.id in ids])

    async def active_runs(self) -> list[ActiveRun]:
        return [ActiveRun(run=r, alive=r.id in self.alive) for r in self.runs if r.active]


class FakeTickets:
    """Tickets by id: their ask, and the facts the page reads."""

    def __init__(
        self,
        asks: dict[str, TicketAsk] | None = None,
        facts: Sequence[TicketFacts] = (),
        repositories: Sequence[RepositoryRef] = (),
    ) -> None:
        self.asks = asks
        self.facts = list(facts)
        self.repository_list = list(repositories)
        self.since: float | None = None

    async def team_facts(self, since: float) -> list[TicketFacts]:
        self.since = since
        return list(self.facts)

    async def repositories(self) -> list[RepositoryRef]:
        return list(self.repository_list)

    async def ticket_ask(self, ticket_id: str) -> TicketAsk:
        if self.asks is None:
            return TicketAsk(kind="feature", labels="", repository="sample")
        if ticket_id not in self.asks:
            raise NotFoundError(f"{ticket_id} does not exist")
        return self.asks[ticket_id]


class FakeGates:
    def __init__(self, gates: Sequence[RunningGate] = ()) -> None:
        self.gates = list(gates)

    async def running_gates(self) -> list[RunningGate]:
        return list(self.gates)


class FakeOwner:
    def __init__(self, items: Sequence[OwnerItem] = ()) -> None:
        self.items = list(items)

    async def owner_items(self) -> list[OwnerItem]:
        return list(self.items)


class FakeSessions:
    def __init__(self, at_work: Sequence[AtWork] = ()) -> None:
        self.at_work = list(at_work)

    async def subagents_at_work(self) -> list[AtWork]:
        return list(self.at_work)


class FakeJobs:
    def __init__(self, jobs: Sequence[LandJob] = ()) -> None:
        self.jobs = list(jobs)

    async def running_land_jobs(self) -> list[LandJob]:
        return list(self.jobs)


class FakeGit(GitFacts):
    """Answers tags and first-commit logs from memory; counts its reads."""

    def __init__(
        self, tags: Sequence[tuple[str, float]] = (), logs: dict[str, str] | None = None
    ) -> None:
        super().__init__()
        self.tag_list = list(tags)
        self.logs = logs or {}
        self.reads: list[str] = []

    @override
    async def tags(self, repository: str) -> list[tuple[str, float]]:
        self.reads.append(f"tags {repository}")
        return list(self.tag_list)

    @override
    async def first_commit_log(self, repository: str, since: float) -> str:
        self.reads.append(f"log {repository} {since:.0f}")
        return self.logs.get(repository, "")


class Fakes:
    """Every fake port, and the `TeamPorts` over them."""

    def __init__(self) -> None:
        self.agents = FakeAgents()
        self.runs = FakeRuns()
        self.tickets = FakeTickets()
        self.gates = FakeGates()
        self.owner = FakeOwner()
        self.sessions = FakeSessions()
        self.jobs = FakeJobs()

    def ports(self) -> TeamPorts:
        return TeamPorts(
            agents=self.agents,
            runs=self.runs,
            tickets=self.tickets,
            gates=self.gates,
            owner=self.owner,
            sessions=self.sessions,
            jobs=self.jobs,
        )
