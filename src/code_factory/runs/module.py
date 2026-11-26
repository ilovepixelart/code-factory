"""The `runs` module as the platform sees it."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from code_factory.agents.service import AgentService
from code_factory.board.models import RunCard, RunRecord, TicketRuns
from code_factory.board.models import RunCost as CardCost
from code_factory.board.service import CardRuns
from code_factory.broker.service import BrokerService
from code_factory.factory.models import RunCost, RunFact
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.errors import NotFoundError
from code_factory.platform.module import Module, Resources
from code_factory.platform.served import Served
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.runs import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.runs.adapters.processes import ProcessRegistry
from code_factory.runs.cli import halt_command, resume_command, run_agent_command, runs_command
from code_factory.runs.models import Run
from code_factory.runs.ports import HookCommandSource, RunPorts
from code_factory.runs.routes import router
from code_factory.runs.rules.records import state_of
from code_factory.runs.service import RunService
from code_factory.runs.service.flow import FlowAdapter
from code_factory.runs.service.keeper import run_keeper
from code_factory.runs.service.launching import RunLauncher
from code_factory.runs.service.neighbours import (
    AgentsAdapter,
    ConfigAdapter,
    MemoryAdapter,
    PreviewSetupAdapter,
    TeamRunSource,
    TeamsAdapter,
    TicketsAdapter,
    TreesAdapter,
)
from code_factory.runs.service.permissions import PermissionService
from code_factory.runs.service.previews import PreviewService
from code_factory.runs.service.tokens import TokensAdapter
from code_factory.settings.service import SettingsService
from code_factory.team.service import RunSource

BOARD = "board"


def _at(moment: float) -> datetime:
    return datetime.fromtimestamp(moment, UTC)


def _fact(run: Run) -> RunFact:
    return RunFact(
        id=run.id,
        ticket_id=run.ticket_key or None,
        repository=run.repository,
        stage=run.stage,
        agent=run.agent,
        model=run.model,
        source=BOARD,
        state=state_of(run),
        started_at=run.started_at.timestamp(),
    )


class BoardRuns:
    """Runs of the board, as the factory counts them."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def runs(self, since: float, until: float) -> list[RunFact]:
        """Runs started in `[since, until)`."""
        found = await self._services.get(RunService).runs_since(_at(since))
        return [_fact(r) for r in found if r.started_at.timestamp() < until]

    async def for_tickets(self, ticket_ids: Sequence[str]) -> list[RunFact]:
        """Every run of the tickets."""
        runs = self._services.get(RunService)
        return [_fact(r) for ticket in ticket_ids for r in await runs.runs_on_ticket(ticket)]


class RunCosts:
    """What each run cost, as the runtime reported it."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def costs(self, run_ids: Sequence[str]) -> dict[str, RunCost]:
        """Cost, whether it was estimated, and tokens, by run id."""
        runs = await self._services.get(RunService).runs_by_ids(list(run_ids))
        return {
            r.id: RunCost(cost=r.cost, estimated=r.cost_estimated, tokens=r.tokens) for r in runs
        }


class BrokerRuns:
    """Run lifetime and halt operations used by the provider broker."""

    def __init__(self, runs: RunService) -> None:
        self._runs = runs

    async def active_run_ids(self, ids: Sequence[str]) -> set[str]:
        """Allow the broker to expire tokens of ended runs."""
        return {run.id for run in await self._runs.runs_by_ids(ids) if run.exit_code is None}

    async def halt_run(self, run_id: str, reason: str) -> None:
        """End a run when its provider cannot continue."""
        await self._runs.halt_run(run_id, reason)


def _total(values: Sequence[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return float(sum(known)) if known else None


def _cost(runs: Sequence[Run]) -> CardCost:
    turns = [r.turns for r in runs if r.turns is not None]
    return CardCost(
        total=_total([r.cost for r in runs]),
        review=_total([r.cost for r in runs if r.stage == "review"]),
        cache_read=_total([r.cache_read for r in runs]),
        turns=sum(turns) if turns else None,
    )


def _card(run: Run, max_iterations: int) -> RunCard:
    return RunCard(
        id=run.id, stage=run.stage, iteration=run.iteration, loop=run.looping,
        max_iterations=max_iterations, attempt=run.attempt, agent=run.agent,
        started_at=run.started_at.timestamp(),
    )  # fmt: skip


class CardRunsAdapter:
    """`CardRuns` over the run service: a card's active runs, what they spent, why they stopped."""

    def __init__(
        self,
        runs: RunService,
        agents: AgentService,
        settings: SettingsService,
        repositories: RepositoryService,
    ) -> None:
        self._runs = runs
        self._agents = agents
        self._settings = settings
        self._repositories = repositories

    async def card_runs(self, ticket_ids: Sequence[str]) -> dict[str, TicketRuns]:
        """The runs of each ticket that has any, newest first; two reads for all the tickets."""
        views = await self._runs.card_runs(ticket_ids)
        listed = [v.id for found in views.values() for v in found]
        full = {r.id: r for r in await self._runs.runs_by_ids(listed)} if listed else {}
        caps: dict[str, int] = {}
        answer: dict[str, TicketRuns] = {}
        for ticket_id, found in views.items():
            runs = [full[v.id] for v in found if v.id in full]
            if runs:
                answer[ticket_id] = await self._ticket_runs(runs, caps)
        return answer

    async def _ticket_runs(self, runs: list[Run], caps: dict[str, int]) -> TicketRuns:
        cost = _cost(runs)
        active = []
        for run in runs:
            if run.exit_code is None:
                if run.repository not in caps:
                    caps[run.repository] = await self._max_iterations(run.repository)
                active.append(_card(run, caps[run.repository]))
        newest = runs[0]
        limited = newest.limited_until
        return TicketRuns(
            runs=active,
            spent=cost.total,
            spent_estimated=any(r.cost_estimated for r in runs if r.cost is not None),
            cost=cost,
            halted=newest.halted,
            limited_until=None if limited is None else limited.timestamp(),
        )

    async def _max_iterations(self, repository: str) -> int:
        try:
            config = await self._settings.load(await self._repositories.get(repository))
        except NotFoundError:
            return self._agents.kit.max_iterations(None)
        return self._agents.kit.max_iterations(
            None if config.agents is None else config.agents.max_iterations
        )

    async def run_records(self, run_ids: Sequence[str]) -> dict[str, RunRecord]:
        """The memory version and context time of each run that recorded either."""
        return {
            r.id: RunRecord(
                memory=None if r.memory_digest is None else {"digest": r.memory_digest},
                context_at=None if r.context_at is None else r.context_at.timestamp(),
            )
            for r in (await self._runs.runs_by_ids(list(run_ids)) if run_ids else [])
            if r.memory_digest is not None or r.context_at is not None
        }

    async def cost_between(self, repository: str, start: datetime, end: datetime) -> float:
        """What the repository's runs started in `[start, end)` cost."""
        return await self._runs.cost_between(repository, start, end)


def _provide(
    services: Services, resources: Resources, hooks_of: Callable[[Services], HookCommandSource]
) -> None:
    registry = ProcessRegistry()
    launcher = RunLauncher(services, resources.settings, hooks_of(services))
    ports = RunPorts(
        tickets=TicketsAdapter(services),
        teams=TeamsAdapter(services),
        trees=TreesAdapter(services),
        agents=AgentsAdapter(services, launcher),
        tokens=TokensAdapter(services, resources.settings.state_dir),
        memory=MemoryAdapter(services),
        config=ConfigAdapter(services),
        flow=FlowAdapter(services),
    )
    state_dir = resources.settings.state_dir
    runs = RunService(resources.uow, ports, registry, state_dir=state_dir)
    services.get(BrokerService).attach_run_control(BrokerRuns(runs))
    board = services.get(Served).base_url or "http://localhost"
    services.add(RunService, runs)
    services.add(PermissionService, PermissionService(resources.uow, ports.config))
    services.add(
        PreviewService,
        PreviewService(
            resources.uow,
            ports,
            PreviewSetupAdapter(services),
            registry,
            state_dir=state_dir,
            board=board,
        ),
    )
    services.add(RunSource, TeamRunSource(lambda: runs))
    services.add(
        CardRuns,
        CardRunsAdapter(
            runs,
            services.get(AgentService),
            services.get(SettingsService),
            services.get(RepositoryService),
        ),
    )
    resources.on_stopping.append(registry.detach_all)  # runs outlive the board: none is signalled


def _background(services: Services, tasks: BackgroundTasks) -> None:
    runs = services.get(RunService)
    permissions = services.get(PermissionService)
    previews = services.get(PreviewService)
    tasks.start("run-keeper", lambda: run_keeper(runs, permissions, previews))


def build_module(hooks_of: Callable[[Services], HookCommandSource]) -> Module:
    """The module, its runs started with the hooks `code_factory.app` takes from their owner."""
    return Module(
        name="runs",
        provide=lambda services, resources: _provide(services, resources, hooks_of),
        commands=(halt_command, resume_command, runs_command, run_agent_command),
        background=_background,
        router=router,
    )
