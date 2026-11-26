"""Fixtures of the stage tests: the service over real ticket, release, repository and settings
services on the isolated test database, with fake git facts and a settable clock."""

from pathlib import Path

import pytest

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
from stage_fakes import FakeClock, FakeFacts
from ticket_values import OWNER

REPOSITORY = "sample"


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def facts() -> FakeFacts:
    return FakeFacts()


@pytest.fixture
async def checkout(tmp_path: Path, repositories: RepositoryService) -> Path:
    """The tracked checkout `sample`."""
    root = tmp_path / REPOSITORY
    root.mkdir()
    await repositories.track(root)
    return root


@pytest.fixture
def releases(uow: UnitOfWork, tickets: TicketService, clock: FakeClock) -> ReleaseService:
    return ReleaseService(uow, tickets, clock=clock)


@pytest.fixture
def stages(  # noqa: PLR0913, PLR0917  # one fixture per service the module reads
    uow: UnitOfWork,
    tickets: TicketService,
    reviews: ReviewService,
    activity: ActivityService,
    documents: DocumentService,
    releases: ReleaseService,
    repositories: RepositoryService,
    checkout: Path,  # noqa: ARG001  # the repository must be tracked
    facts: FakeFacts,
    clock: FakeClock,
) -> StageService:
    ports = Ports(
        tickets=tickets,
        reviews=reviews,
        activity=activity,
        documents=documents,
        releases=releases,
        repositories=repositories,
        settings=SettingsService(uow),
        facts=facts,
    )
    return StageService(uow, ports, clock=clock)


@pytest.fixture
async def started(tickets: TicketService) -> Ticket:
    """A ticket in `sample` with its branch declared."""
    made = await tickets.create(NewTicket(repository=REPOSITORY, title="A ticket"), by=OWNER)
    return await tickets.set_branch(made.id, "feat/CF-1", by=OWNER)
