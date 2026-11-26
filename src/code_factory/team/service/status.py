"""What each agent is doing and how its latest run ended, its lanes, caps and the queue's rule."""

from code_factory.platform.errors import NotFoundError
from code_factory.team import rules
from code_factory.team.models import Ask, Doing, Lanes, Last, Lease, TeamAgent, TeamRun
from code_factory.team.repository import LeaseRepository
from code_factory.team.service.base import DAY, ServiceBase, fan_out, merged, together
from code_factory.team.service.ports import TeamPorts

_RUNS = "the runs"

LANE_WINDOW = 21_600.0


class Status(ServiceBase):
    """Reads that say what the agents do; none writes."""

    async def _leases(self) -> dict[str, Lease]:
        async with self._uow() as session:
            return await LeaseRepository(session).all()

    async def _agents_and_leases(
        self, ports: TeamPorts
    ) -> tuple[list[TeamAgent], dict[str, Lease]]:
        async with together() as group:
            agents = group.create_task(self._read("the agents", ports.agents.team_agents()))
            leases = group.create_task(self._leases())
        return agents.result(), leases.result()

    async def _repository_of(self, ticket_id: str) -> str:
        try:
            asked = await self._read("the ticket", self._ports().tickets.ticket_ask(ticket_id))
        except NotFoundError:
            return ""
        return asked.repository

    async def _situation(
        self, now: float, *, window: float | None = None
    ) -> tuple[list[TeamAgent], dict[str, Lease], list[TeamRun], dict[str, str]]:
        """The agents, the claims, the runs they read and the repository of each claimed ticket."""
        ports = self._ports()
        agents, leases = await self._agents_and_leases(ports)
        names = [agent.name for agent in agents]
        latest = await self._read(_RUNS, ports.runs.latest_runs(names))
        extra: list[TeamRun] = []
        if window is not None:
            async with together() as group:
                started = group.create_task(self._read(_RUNS, ports.runs.runs_since(window)))
                active = group.create_task(self._read(_RUNS, ports.runs.active_runs()))
            extra = merged(started.result(), [item.run for item in active.result()])
        tickets = sorted({*leases, *(run.ticket_id for run in [*latest, *extra] if run.ticket_id)})
        runs = await self._runs_for(
            tickets,
            agents,
            sorted({r for lease in leases.values() for r in lease.runs}),
            now,
            ports=ports,
        )
        found = await fan_out([self._repository_of(key) for key in leases])
        repositories = dict(zip(leases, found, strict=True))
        return agents, leases, merged(extra, runs), repositories

    async def doing(self, now: float | None = None) -> dict[str, Doing]:
        """What each defined agent that is not idle is doing."""
        at = self._seconds(now)
        agents, leases, runs, repositories = await self._situation(at)
        return rules.doing(agents, leases, runs, at, repositories)

    async def last(self, now: float | None = None) -> dict[str, Last]:
        """How each defined agent's latest run ended."""
        at = self._seconds(now)
        agents, _leases, runs, repositories = await self._situation(at)
        return rules.last(agents, runs, repositories)

    async def lanes(self, now: float | None = None) -> Lanes:
        """The agents' runs of the last six hours, and the waits between a ticket's runs."""
        at = self._seconds(now)
        since = at - LANE_WINDOW
        agents, leases, runs, repositories = await self._situation(at, window=since)
        found = rules.lanes(agents, runs, leases, (since, at), repositories)
        return Lanes(since=since, now=at, lanes=found, chains=rules.chains(found))

    async def over_cap(self, agent_name: str, ticket_id: str) -> str | None:
        """The cap the agent reached on the ticket or on its day; `None` within them."""
        ports = self._ports()
        at = self._seconds(None)
        async with together() as group:
            defined = group.create_task(self._read("the agents", ports.agents.team_agents()))
            here = group.create_task(self._read(_RUNS, ports.runs.runs_on_ticket(ticket_id)))
            today = group.create_task(self._read(_RUNS, ports.runs.runs_since(at // DAY * DAY)))
        agents = defined.result()
        agent = next((a for a in agents if a.name == agent_name), None)
        if agent is None:
            return None
        return rules.at_cap(
            agent, Ask(key=ticket_id, runs=tuple(merged(today.result(), here.result())), now=at)
        )

    async def queue_rule(self, ticket_ids: list[str] | None = None) -> rules.QueueRule:
        """The queue's pure rule over the agents, runs and claims as they are now.

        `ticket_ids` are the cards the queue plans: their runs are read so the rule can tell who
        wrote what and what each agent spent on them. Without them the cards are the open tickets.
        """
        at = self._seconds(None)
        ports = self._ports()
        agents, leases = await self._agents_and_leases(ports)
        if ticket_ids is None:
            open_tickets = await self._read("the tickets", ports.tickets.team_facts(at))
            ticket_ids = [facts.reference.id for facts in open_tickets]
        runs = await self._runs_for(
            ticket_ids,
            agents,
            sorted({r for lease in leases.values() for r in lease.runs}),
            at,
            ports=ports,
        )
        team = rules.Team(
            agents=tuple(agents), runs=tuple(runs), busy=rules.busy(leases, runs, at), now=at
        )
        return rules.QueueRule(team)
