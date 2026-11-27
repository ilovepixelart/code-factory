"""The `checks` module as the platform sees it.

List it after tickets, git, releases, repositories, settings, agents, stages and team: it reads
their services. It registers the team's gate source and gives the stages module its log
reader. Its srt settings come from the agents kit's rules (`adapters/sandbox.py`), its forge from
`app.py`. The supervisor and the keeper start with the HTTP app;
`CODE_FACTORY_CHECKS_CONCURRENCY` bounds the runs at once (default 4).
"""

import os
from collections.abc import Callable, Sequence
from functools import partial

from code_factory.agents.service import AgentService
from code_factory.board.models import CheckRecord
from code_factory.board.service import CardChecks
from code_factory.checks import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.checks.adapters.sandbox import KitSandbox
from code_factory.checks.cli import checks_command
from code_factory.checks.models import CheckRecord as StoredCheckRecord
from code_factory.checks.ports import ForgePort
from code_factory.checks.routes import router
from code_factory.checks.service import CheckDeps, CheckOptions, CheckService
from code_factory.git.service import GitService
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.db import try_session_lock
from code_factory.platform.errors import SettingsError
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.platform.text import stamp
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.settings.service import SettingsService
from code_factory.stages.service import StageService
from code_factory.team.models import RunningGate
from code_factory.team.service import GateSource
from code_factory.tickets.service import ActivityService, TicketService

CONCURRENCY_VARIABLE = "CODE_FACTORY_CHECKS_CONCURRENCY"
NO_VERDICT = -1  # a checks record without an exit code: the card rules give it no say
DEFAULT_CONCURRENCY = 4


class GitChecks:
    """Git's view of the board's checks: asked when used, since checks is built after git."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def verdict(self, repository: str, ticket_id: str, head: str) -> str:
        """The checks verdict of a head, as the merge reads it."""
        return await self._services.get(CheckService).verdict(repository, ticket_id, head)

    async def configured(self, repository: str) -> bool:
        """Whether the repository sets a checks command."""
        return await self._services.get(CheckService).configured(repository)


class _TeamGates:
    """The team's view of the running checks."""

    def __init__(self, checks: CheckService) -> None:
        self._checks = checks

    async def running_gates(self) -> list[RunningGate]:
        return await self._checks.running_gates()


class CardChecksAdapter:
    """`CardChecks` over the check service."""

    def __init__(self, checks: CheckService) -> None:
        self._checks = checks

    async def latest_checks(self, heads: dict[str, str]) -> dict[str, list[CheckRecord]]:
        """The latest verdict for each supplied head."""
        found = await self._checks.card_records(heads)
        return {ticket: [self._record(r) for r in records] for ticket, records in found.items()}

    async def latest_attempt(self, ticket: str) -> CheckRecord | None:
        """The last attempt, including one with no verdict."""
        record = await self._checks.latest_attempt(ticket)
        return self._record(record) if record else None

    @staticmethod
    def _record(record: StoredCheckRecord) -> CheckRecord:
        return CheckRecord(
            commit=record.commit,
            exit_code=NO_VERDICT if record.exit_code is None else record.exit_code,
            at=stamp(record.at),
            tree=record.tree,
            reason=record.reason,
            log=record.log,
        )

    async def running(self, ticket_ids: Sequence[str]) -> set[str]:
        """The tickets whose checks are queued or run now."""
        return await self._checks.running(ticket_ids)

    async def log_tail(self, ticket_id: str, lines: int) -> str:
        """The last lines of the ticket's newest failing check log."""
        return await self._checks.log_tail(ticket_id, lines)


class _StageLogs:
    """What the stage module may read of a log: only one the checks module wrote."""

    def __init__(self, checks: CheckService) -> None:
        self._checks = checks

    async def read(self, log: str) -> str | None:
        return await self._checks.read_log(log)


def concurrency(environment: dict[str, str] | None = None) -> int:
    """How many runs may go at once: the variable, default 4."""
    given = (environment if environment is not None else os.environ).get(CONCURRENCY_VARIABLE)
    if given is None or not given.strip():
        return DEFAULT_CONCURRENCY
    if not given.strip().isdigit() or int(given) < 1:
        msg = f"{CONCURRENCY_VARIABLE} is {given!r}: write how many runs may go at once, as 4"
        raise SettingsError(msg)
    return int(given)


def build_module(forge_of: Callable[[Services], ForgePort]) -> Module:
    """The module over the forge `forge_of` builds from the registry (`code_factory.app`)."""

    def provide(services: Services, resources: Resources) -> None:
        sandbox = KitSandbox(
            services.get(AgentService),
            services.get(SettingsService),
            services.get(RepositoryService),
            resources.settings.state_dir,
        )
        deps = CheckDeps(
            tickets=services.get(TicketService),
            activity=services.get(ActivityService),
            stages=services.get(StageService),
            git=services.get(GitService),
            settings=services.get(SettingsService),
            repositories=services.get(RepositoryService),
            releases=services.get(ReleaseService),
            agents=services.get(AgentService),
            forge=forge_of(services),
            sandbox=sandbox,
            denials=sandbox,
            verify_claim=partial(try_session_lock, resources.engine),
        )
        options = CheckOptions(
            state_dir=resources.settings.state_dir,
            concurrency=concurrency(),
            shutdown_s=float(resources.settings.shutdown_timeout_s),
        )
        service = CheckService(resources.uow, deps, options)
        services.add(CheckService, service)
        services.add(GateSource, _TeamGates(service))
        services.add(CardChecks, CardChecksAdapter(service))
        services.get(StageService).bind_log_reader(_StageLogs(service))
        resources.on_stop.append(service.drain)

    def background(services: Services, tasks: BackgroundTasks) -> None:
        service = services.get(CheckService)
        tasks.start("checks-supervisor", service.run_supervisor)
        tasks.start("checks-keeper", service.run_keeper)

    return Module(
        name="checks",
        provide=provide,
        commands=(checks_command,),
        background=background,
        router=router,
    )
