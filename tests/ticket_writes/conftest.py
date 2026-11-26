"""Fixtures of the ticket write tests: the service over the real ticket, stage, repository and
undo services on the isolated test database, fake git and a settable clock."""

from pathlib import Path

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.settings.service import SettingsService
from code_factory.stages.service import Ports, StageService
from code_factory.ticket_writes.service import TicketWriteService, WritePorts
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)
from code_factory.undo.service import UndoService
from stage_fakes import FakeClock, FakeFacts
from write_fakes import FakeGit

REPOSITORIES = ("sample", "second")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def facts() -> FakeFacts:
    return FakeFacts()


@pytest.fixture
def git() -> FakeGit:
    return FakeGit()


@pytest.fixture(autouse=True)
async def tracked(tmp_path: Path, repositories: RepositoryService) -> None:
    """`sample` and `second` are tracked repositories."""
    for name in REPOSITORIES:
        root = tmp_path / name
        root.mkdir()
        await repositories.track(root)


@pytest.fixture
def undo(uow: UnitOfWork, clock: FakeClock) -> UndoService:
    return UndoService(uow, clock)


@pytest.fixture
def stages(  # noqa: PLR0913, PLR0917  # one fixture per service the module reads
    uow: UnitOfWork,
    tickets: TicketService,
    reviews: ReviewService,
    activity: ActivityService,
    documents: DocumentService,
    repositories: RepositoryService,
    facts: FakeFacts,
    clock: FakeClock,
) -> StageService:
    ports = Ports(
        tickets=tickets,
        reviews=reviews,
        activity=activity,
        documents=documents,
        releases=ReleaseService(uow, tickets, clock=clock),
        repositories=repositories,
        settings=SettingsService(uow),
        facts=facts,
    )
    return StageService(uow, ports, clock=clock)


@pytest.fixture
def writes(  # noqa: PLR0913, PLR0917  # the service and everything it is built from
    uow: UnitOfWork,
    tickets: TicketService,
    stages: StageService,
    git: FakeGit,
    repositories: RepositoryService,
    undo: UndoService,
    clock: FakeClock,
) -> TicketWriteService:
    ports = WritePorts(tickets=tickets, stages=stages, git=git, repositories=repositories)
    return TicketWriteService(uow, ports, undo, clock=clock)
