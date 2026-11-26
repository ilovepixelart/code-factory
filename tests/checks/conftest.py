"""Fixtures of the checks tests: the service over real services, a real repository, fakes for
the forge and the sandbox, a movable clock and a state folder in `tmp_path`."""

from pathlib import Path

import pytest

from checks_support import (
    ENGINE_SCRIPT,
    REPO,
    Clock,
    FakeForge,
    FakeSandbox,
    branch_with,
    script,
)
from code_factory.agents.service import AgentService
from code_factory.checks.service import CheckDeps, CheckOptions, CheckService
from code_factory.git.service import GitService
from code_factory.platform.db import UnitOfWork
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.settings.service import SettingsService
from code_factory.stages.service import Ports, StageService
from code_factory.tickets.models import NewTicket, Ticket
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)
from git_support import Fakes, make_repo, make_service
from stage_fakes import FakeFacts
from ticket_values import OWNER


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def forge() -> FakeForge:
    return FakeForge()


@pytest.fixture
def sandbox() -> FakeSandbox:
    return FakeSandbox()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """The checkout `sample` with an origin and one commit on main."""
    return make_repo(tmp_path)


@pytest.fixture
def state(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
async def tracked(root: Path, repositories: RepositoryService) -> Path:
    await repositories.track(root)
    return root


@pytest.fixture
def git_service(uow: UnitOfWork, root: Path) -> GitService:
    return make_service(uow, Fakes(roots={REPO: root}))


@pytest.fixture
def releases(uow: UnitOfWork, tickets: TicketService, clock: Clock) -> ReleaseService:
    return ReleaseService(uow, tickets, clock=clock)


@pytest.fixture
def options(state: Path) -> CheckOptions:
    """No beat during a test: the unit of work is one connection a second task must not use."""
    return CheckOptions(state_dir=state, heartbeat_s=3600.0, turn_poll_s=0.01, shutdown_s=1.0)


@pytest.fixture
def checks(  # one fixture per service the module reads
    uow: UnitOfWork,
    tickets: TicketService,
    activity: ActivityService,
    documents: DocumentService,
    reviews: ReviewService,
    repositories: RepositoryService,
    releases: ReleaseService,
    git_service: GitService,
    forge: FakeForge,
    sandbox: FakeSandbox,
    options: CheckOptions,
    clock: Clock,
    tracked: Path,  # noqa: ARG001  # the repository must be tracked
) -> CheckService:
    settings = SettingsService(uow)
    stages = StageService(
        uow,
        Ports(
            tickets=tickets,
            reviews=reviews,
            activity=activity,
            documents=documents,
            releases=releases,
            repositories=repositories,
            settings=settings,
            facts=FakeFacts(),
        ),
        clock=clock,
    )
    deps = CheckDeps(
        tickets=tickets,
        activity=activity,
        stages=stages,
        git=git_service,
        settings=settings,
        repositories=repositories,
        releases=releases,
        agents=AgentService(uow),
        forge=forge,
        sandbox=sandbox,
        denials=sandbox,
    )
    return CheckService(uow, deps, options, clock)


@pytest.fixture
async def started(tickets: TicketService, root: Path) -> Ticket:
    """A ticket of `sample` on branch `ticket/cf-1`, which holds one commit."""
    made = await tickets.create(NewTicket(repository=REPO, title="A ticket"), by=OWNER)
    branch_with(root, "ticket/cf-1", **{"work.txt": "work\n"})
    return await tickets.set_branch(made.id, "ticket/cf-1", by=OWNER)


@pytest.fixture
def out(tmp_path: Path) -> Path:
    folder = tmp_path / "out"
    folder.mkdir()
    return folder


@pytest.fixture
def engine(tmp_path: Path, out: Path) -> Path:
    return script(tmp_path / "bin" / "engine", ENGINE_SCRIPT.format(out=out))
