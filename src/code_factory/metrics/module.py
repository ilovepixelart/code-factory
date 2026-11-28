"""The `metrics` module as the platform sees it.

The adapters here are the only place another module is imported: each wraps an owning service in
the port this module reads. The runs module is listed after this one, so its service is asked
when a port is read.
"""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from code_factory.board.service import MergeLedger
from code_factory.checks.service import CheckService
from code_factory.git.service import GitService
from code_factory.metrics import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.metrics.adapters import GitReader
from code_factory.metrics.cli import metrics_command
from code_factory.metrics.models import (
    CheckRecord,
    RunFacts,
    StageMove,
    StepRun,
    TicketFlow,
    TrackedRepo,
)
from code_factory.metrics.ports import MetricsPorts
from code_factory.metrics.routes import router
from code_factory.metrics.service import MetricsService
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.runs.service import RunService
from code_factory.tickets.models import Column
from code_factory.tickets.service import TicketService


class RepositoriesAdapter:
    """Tracked repositories; the default branch is asked of git only when a pass needs it."""

    def __init__(self, repositories: RepositoryService, git: GitService) -> None:
        self._repositories = repositories
        self._git = git

    async def tracked(self) -> list[TrackedRepo]:
        """Every tracked repository, its checkout and default branch."""
        return [
            TrackedRepo(name=record.name, path=Path(record.path))
            for record in await self._repositories.list()
        ]

    async def default_branch(self, name: str) -> str:
        """The default branch git reports for the repository."""
        return (await self._git.facts(name)).default_branch


class TicketsAdapter:
    """Ticket flow facts. The card's "needs next" sentence is not a ticket field yet: empty."""

    def __init__(self, tickets: TicketService) -> None:
        self._tickets = tickets

    async def flow_facts(
        self,
        repository: str,
        ids: Sequence[str] | None = None,
        stages: Sequence[str] | None = None,
        causes: Sequence[str] | None = None,
    ) -> list[TicketFlow]:
        """The repository's tickets with their moves, renamed into this module's values.

        The ticket service has no filter on a cause yet, so `causes` narrows what it returns here.
        """
        columns = None if stages is None else [Column(s) for s in stages]
        found = await self._tickets.flow_facts(
            repository, None if ids is None else list(ids), columns
        )
        found = [t for t in found if causes is None or set(causes) & set(t.caused_by)]
        return [
            TicketFlow(
                id=t.id,
                title=t.title,
                stage=t.stage.value,
                archived=t.archived,
                branch=t.branch,
                created_at=t.created_at,
                caused_by=list(t.caused_by),
                needs="",
                moves=[StageMove(at=m.at, to=m.to.value) for m in t.moves],
            )
            for t in found
        ]


class RunsAdapter:
    """The runs of the run service, renamed into this module's values."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def since(self, since: datetime) -> list[RunFacts]:
        """Runs started at or after `since`, of every repository."""
        return [
            RunFacts(
                repository=run.repository,
                ticket_id=run.ticket_key,
                stage=run.stage,
                agent=run.agent,
                model=run.model,
                connection=run.connection,
                started_at=run.started_at,
                exit_code=run.exit_code,
                halted=run.halted,
                tokens=run.tokens,
                cost=run.cost,
                cost_estimated=run.cost_estimated,
                commits=run.commits,
            )
            for run in await self._services.get(RunService).runs_since(since)
        ]

    async def build_starts(
        self, repository: str, since: datetime, until: datetime
    ) -> dict[str, datetime]:
        """The first Build run start of each ticket inside the window."""
        starts: dict[str, datetime] = {}
        for run in await self._services.get(RunService).build_starts(repository, since, until):
            starts.setdefault(run.ticket_key, run.started_at)
        return starts


class ChecksAdapter:
    """The `checks` records of the check service, renamed into this module's values."""

    def __init__(self, checks: CheckService) -> None:
        self._checks = checks

    async def records(self, repository: str, tickets: Sequence[str]) -> list[CheckRecord]:
        """The check verdicts recorded for these tickets of the repository, oldest first."""
        return [
            CheckRecord(ticket_id=r.ticket_id, commit=r.commit, exit_code=r.exit_code, at=r.at)
            for r in await self._checks.records(repository, tickets)
        ]

    async def step_runs(
        self, newest: int | None, *, repository: str | None = None
    ) -> list[StepRun]:
        """Recent check phase results, optionally scoped to a repository."""
        return [
            StepRun(
                ticket_id=r.ticket_id,
                at=r.at,
                seconds=r.seconds,
                states=r.states,
                retried=r.retried,
                lock_waits=r.lock_waits,
                slept=r.slept,
            )
            for r in await self._checks.step_runs(newest, repository=repository)
        ]


def _provide(services: Services, resources: Resources) -> None:
    ports = MetricsPorts(
        repositories=RepositoriesAdapter(services.get(RepositoryService), services.get(GitService)),
        tickets=TicketsAdapter(services.get(TicketService)),
        runs=RunsAdapter(services),
        checks=ChecksAdapter(services.get(CheckService)),
    )
    metrics = MetricsService(resources.uow, ports, GitReader())
    services.add(MetricsService, metrics)
    services.add(MergeLedger, metrics)


def _background(services: Services, tasks: BackgroundTasks) -> None:
    tasks.start("metrics-refresh", services.get(MetricsService).run_refresh_loop)


module = Module(
    name="metrics",
    provide=_provide,
    commands=(metrics_command,),
    background=_background,
    router=router,
)
