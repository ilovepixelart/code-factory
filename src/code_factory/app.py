"""The composition root: the one place that knows every module.

Adding a module is two lines here: import its `module` and append it to `MODULES`. List a module
after the modules whose services it uses. Alembic imports this file, so each module's tables
reach the migration metadata through the `module.py` that imports them.
"""

import os
import sys
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, override

from code_factory.about.module import module as about
from code_factory.agents.module import module as agents
from code_factory.auth.models import TokenKind
from code_factory.auth.module import module as auth
from code_factory.auth.service import AuthService
from code_factory.board.module import module as board
from code_factory.broker.module import module as broker
from code_factory.checks.module import GitChecks
from code_factory.checks.module import build_module as build_checks
from code_factory.commands.module import module as commands
from code_factory.delivery.module import ChecksForge, DeliveredPulls, GitForge
from code_factory.delivery.module import module as delivery
from code_factory.evals.module import ScorerAnswers
from code_factory.evals.module import module as evals
from code_factory.factory.models import Improvements
from code_factory.factory.module import build_module as build_factory
from code_factory.factory.service import FactoryPorts, ImprovementPort
from code_factory.follower.module import module as follower
from code_factory.git.models import HookOutcome, TicketRef
from code_factory.git.module import build_module as build_git
from code_factory.git.service import GitPorts, HooksPort
from code_factory.health.module import module as health
from code_factory.hooks.module import RunHookCommands
from code_factory.hooks.module import module as hooks
from code_factory.inbox.module import module as inbox
from code_factory.memory.module import module as memory
from code_factory.memory_extras.module import module as memory_extras
from code_factory.metrics.module import module as metrics
from code_factory.platform import cli
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.cli import SIGN_IN_PREFIX
from code_factory.platform.config import Settings
from code_factory.platform.db import (
    AsyncSession,
    NoDatabase,
    UnitOfWork,
    async_sessionmaker,
    create_engine,
    create_session_factory,
)
from code_factory.platform.errors import NotFoundError, SettingsError
from code_factory.platform.mcp import Access, build_mcp
from code_factory.platform.module import Module, Resources
from code_factory.platform.runtime import run_on_stop, running
from code_factory.platform.served import Served
from code_factory.platform.services import Services
from code_factory.platform.web.app import WebOptions, create_web_app
from code_factory.platform.web.guard import SessionCheck
from code_factory.platform.web.lifespan import StartupLines
from code_factory.platform.web.webapp import DEFAULT_APP_DIR
from code_factory.push.module import module as push
from code_factory.releases.module import module as releases
from code_factory.repositories.module import module as repositories
from code_factory.repositories.service import RepositoryService
from code_factory.runs.module import BoardRuns, RunCosts
from code_factory.runs.module import build_module as build_runs
from code_factory.sample.module import module as sample
from code_factory.screens.module import module as screens
from code_factory.sessions.module import module as sessions
from code_factory.settings.module import module as settings_module
from code_factory.stages.module import module as stages
from code_factory.stages.service import StageService
from code_factory.talk.module import module as talk
from code_factory.team.module import module as team
from code_factory.ticket_writes.module import module as ticket_writes
from code_factory.tickets.models import Column
from code_factory.tickets.module import module as tickets
from code_factory.tickets.service import ReviewService, TicketService
from code_factory.timeline.module import module as timeline
from code_factory.undo.module import module as undo

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastmcp import FastMCP

MCP_TOKEN_VARIABLE = "CODE_FACTORY_MCP_TOKEN"  # noqa: S105  # a name, not a secret; the stdio server's credential (never a file)


def _factory_ports(services: Services) -> FactoryPorts:
    """The factory's ports, each over the module that owns the facts."""
    return FactoryPorts(
        runs=BoardRuns(services), pulls=DeliveredPulls(services), costs=RunCosts(services),
        scorers=ScorerAnswers(services), improvements=NoImprovements(),
        repairs=services.get(StageService),
        role_notes=services.get(ReviewService),
    )  # fmt: skip


factory = build_factory(_factory_ports)
runs = build_runs(RunHookCommands)


class NoImprovements(ImprovementPort):
    """Self-improvement pull requests: nothing produces them yet."""

    @override
    async def newest(self, limit: int) -> Improvements:
        """Not available."""
        return Improvements(available=False)


class _Directory:
    """Git's view of the tracked repositories."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def root_of(self, repository: str) -> Path:
        return await self._services.get(RepositoryService).get(repository)

    async def by_path(self, path: Path) -> str:
        found = [
            r
            for r in await self._services.get(RepositoryService).list()
            if path.is_relative_to(r.path)
        ]
        if not found:
            msg = f"{path} is not inside a tracked repository"
            raise NotFoundError(msg)
        return max(found, key=lambda r: len(r.path)).name


class _GitTickets:
    """Git's view of tickets; a ticket is read by id, so the repository only scopes the call."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def ticket(self, repository: str, ticket_id: str) -> TicketRef:  # noqa: ARG002
        ticket = await self._services.get(TicketService).get(ticket_id)
        return TicketRef(
            id=ticket.id, title=ticket.title, kind=ticket.type, labels=ticket.labels,
            branch=ticket.branch, blocker_ids=ticket.blocked_by,
        )  # fmt: skip

    async def record_branch(self, repository: str, ticket_id: str, branch: str) -> None:  # noqa: ARG002
        await self._services.get(TicketService).set_branch(ticket_id, branch, by="board")

    async def stack_parent(self, repository: str, ticket_id: str) -> str | None:  # noqa: ARG002
        """The one unmerged blocker in Build or Review with a branch that waits on nothing."""
        tickets = self._services.get(TicketService)
        blockers = [await tickets.get(b) for b in (await tickets.get(ticket_id)).blocked_by]
        open_ones = [b for b in blockers if b.column is not Column.MERGED]
        if len(open_ones) != 1:
            return None
        parent = open_ones[0]
        waiting = any(
            [(await tickets.get(b)).column is not Column.MERGED for b in parent.blocked_by]
        )
        in_flight = parent.column in {Column.BUILD, Column.REVIEW}
        return parent.branch if in_flight and parent.branch and not waiting else None


class _NoSetup(HooksPort):
    """No setup command until a module owns one."""

    @override
    async def setup_command(self, repository: str) -> str | None:
        return None

    @override
    async def run_setup(self, repository: str, ticket_id: str, tree: Path) -> HookOutcome:
        return HookOutcome(code=0)


def _git_ports(services: Services) -> GitPorts:
    """Adapters over the services git reads."""
    forge = GitForge(services)
    return GitPorts(
        directory=_Directory(services), tickets=_GitTickets(services),
        forge=forge, checks=GitChecks(services), screen=forge, hooks=_NoSetup(),
    )  # fmt: skip


git = build_git(_git_ports)


checks = build_checks(ChecksForge)

MODULES: tuple[Module, ...] = (
    about,
    auth,
    health,
    settings_module,
    agents,
    team,
    undo,
    repositories,
    talk,
    tickets,
    timeline,
    git,
    memory,
    memory_extras,
    releases,
    stages,
    checks,
    metrics,
    ticket_writes,
    sessions,
    broker,
    runs,
    hooks,
    delivery,
    evals,
    follower,
    screens,
    inbox,
    push,
    commands,
    board,
    sample,
    factory,
)


def build_services(
    resources: Resources, modules: Sequence[Module] = MODULES, *, served: Served | None = None
) -> Services:
    """Every module's service, built in the order of `modules`, and what the process serves."""
    services = Services()
    services.add(Served, served or Served.none())
    for module in modules:
        if module.provide is not None:
            module.provide(services, resources)
    return services


def build_resources(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    *,
    database: bool = True,
) -> Resources:
    """The engine (nothing connects until first use) and unit of work of this process.

    `session_factory` replaces the engine's sessions; tests bind them to one rolled-back
    connection. Without `database` every use of the unit of work refuses (`NoDatabase`).
    """
    engine = create_engine(settings)
    uow = (
        UnitOfWork(session_factory or create_session_factory(engine)) if database else NoDatabase()
    )
    return Resources(settings, engine, uow, BackgroundTasks())


def _session_check(services: Services) -> SessionCheck:
    """Accepts a cookie value that is a live owner session, and nothing else."""
    auth = services.get(AuthService)

    async def check(cookie: str) -> bool:
        return await auth.verify_token(cookie, kinds={TokenKind.SESSION}) is not None

    return check


def _sign_in_lines(services: Services, settings: Settings) -> StartupLines:
    auth = services.get(AuthService)
    served = services.get(Served)
    base_url = served.base_url if served.serving else settings.base_url

    async def lines() -> list[str]:
        nonce = (await auth.issue_sign_in_nonce("owner")).token.get_secret_value()
        return [f"{SIGN_IN_PREFIX}{base_url}/owner/{nonce}"]

    return lines


def create_app(  # noqa: PLR0913  # the seams a test replaces, all optional
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    *,
    app_dir: Path = DEFAULT_APP_DIR,
    guarded: bool = True,
    served: Served | None = None,
    modules: Sequence[Module] = MODULES,
) -> FastAPI:
    """The HTTP app over `modules` (every module), serving the web app built in `app_dir`.

    `guarded=False` leaves `/api` open: for tests of routes that are not about the guard.
    `served` says what the serving process listens on.
    """
    resources = build_resources(settings, session_factory)
    services = build_services(resources, modules, served=served)
    return create_web_app(
        resources,
        services=services,
        modules=modules,
        mcp_access=Access(verifier=services.get(AuthService)),
        options=WebOptions(
            app_dir=app_dir,
            session_check=_session_check(services) if guarded else None,
            startup_lines=_sign_in_lines(services, settings) if guarded else None,
        ),
    )


def create_mcp_server(
    settings: Settings,
    modules: Sequence[Module] = MODULES,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FastMCP:
    """The MCP server over every module, for the stdio transport.

    It serves one credential, `CODE_FACTORY_MCP_TOKEN`, verified again on every call. `modules`
    must include `auth`; `session_factory` is for tests, as in `create_app`.
    """
    token = os.environ.get(MCP_TOKEN_VARIABLE)
    if token is None or not token.strip():
        msg = (
            f"{MCP_TOKEN_VARIABLE} is not set; the MCP server runs for one token, which the board "
            "gives a run or `code-factory token create` gives the owner"
        )
        raise SettingsError(msg)
    resources = build_resources(settings, session_factory)
    services = build_services(resources, modules)
    return build_mcp(
        services,
        modules,
        lifespan=lambda _server: running(resources),
        access=Access(verifier=services.get(AuthService), token=token),
    )


@asynccontextmanager
async def open_services(
    settings: Settings, modules: Sequence[Module] = MODULES, *, database: bool = True
) -> AsyncGenerator[Services]:
    """The services of every module on a started runtime, for a CLI command.

    `database=False` skips the schema check and gives services that refuse to use a database.
    """
    resources = build_resources(settings, database=database)
    if not database:
        try:
            yield build_services(resources, modules)
        finally:
            await run_on_stop(resources)
            await resources.engine.dispose()
        return
    async with running(resources):
        yield build_services(resources, modules)


def main(argv: Sequence[str] | None = None) -> int:
    """The `code-factory` command."""
    return cli.main(
        argv,
        create_app=create_app,
        create_mcp=create_mcp_server,
        open_services=open_services,
        modules=MODULES,
    )


if __name__ == "__main__":
    sys.exit(main())
