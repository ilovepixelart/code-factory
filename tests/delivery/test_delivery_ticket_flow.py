"""Delivery moves the ticket: the pull request it opens puts the ticket in Review, its merge in
Merged, over the real tickets and stages services."""

from datetime import timedelta

import pytest

from code_factory.delivery.ports import Candidate, DeliveryPorts
from code_factory.delivery.service import DeliveryService
from code_factory.delivery.service.neighbours import TicketsAdapter
from code_factory.platform.db import UnitOfWork
from code_factory.platform.services import Services
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.settings.service import SettingsService
from code_factory.stages.service import Ports, StageService
from code_factory.tickets.models import PullRequest, PullRequestState, Ticket
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)
from delivery_fakes import URL, Clock, Fakes, Places, ScriptedGh, pull_answer
from stage_fakes import FakeFacts
from ticket_values import OWNER


@pytest.fixture
def gh() -> ScriptedGh:
    return ScriptedGh()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def fakes(ticket: Ticket) -> Fakes:
    """The git, checks and places neighbours; the tickets are the real service."""
    candidate = Candidate(id=ticket.id, repository="sample", title="", branch="", column="")
    return Fakes(ticket=candidate)


@pytest.fixture
async def shipping(tickets: TicketService, ticket: Ticket) -> Ticket:
    return await tickets.set_branch(ticket.id, "ticket/cf-1", by=OWNER)


@pytest.fixture
def delivered(  # noqa: PLR0913, PLR0917  # every service shipping reads
    uow: UnitOfWork,
    tickets: TicketService,
    documents: DocumentService,
    activity: ActivityService,
    fakes: Fakes,
    gh: ScriptedGh,
    clock: Clock,
) -> DeliveryService:
    services = Services()
    services.add(TicketService, tickets)
    services.add(DocumentService, documents)
    services.add(ActivityService, activity)
    ports = DeliveryPorts(
        tickets=TicketsAdapter(services),
        git=fakes,
        checks=fakes,
        places=Places(fakes),
        policy=fakes,
    )
    return DeliveryService(uow, ports, gh, clock=clock)


@pytest.fixture
def stages(  # noqa: PLR0913, PLR0917  # one fixture per service the module reads
    uow: UnitOfWork,
    tickets: TicketService,
    reviews: ReviewService,
    activity: ActivityService,
    documents: DocumentService,
    repositories: RepositoryService,
) -> StageService:
    ports = Ports(
        tickets=tickets,
        reviews=reviews,
        activity=activity,
        documents=documents,
        releases=ReleaseService(uow, tickets),
        repositories=repositories,
        settings=SettingsService(uow),
        facts=FakeFacts(),
    )
    return StageService(uow, ports)


def _ready(gh: ScriptedGh) -> None:
    gh.answer(("pr", "list"), [])
    gh.answer(("pr", "create"), URL + "\n")
    gh.answer(("pr", "view"), pull_answer())


async def test_a_shipped_ticket_records_its_pull_request_and_reaches_review(
    delivered: DeliveryService,
    tickets: TicketService,
    stages: StageService,
    shipping: Ticket,
    gh: ScriptedGh,
) -> None:
    _ready(gh)

    await delivered.ship(shipping.id)

    found = await tickets.get(shipping.id)
    assert found.pull_request == PullRequest(number=9, state=PullRequestState.OPEN, url=URL)
    assert (await stages.assess(shipping.id)).stage == "review"


async def test_a_merged_ticket_reaches_merged_and_its_origin_is_fetched(  # noqa: PLR0913, PLR0917
    delivered: DeliveryService,
    tickets: TicketService,
    stages: StageService,
    shipping: Ticket,
    gh: ScriptedGh,
    fakes: Fakes,
) -> None:
    _ready(gh)
    await delivered.ship(shipping.id)
    gh.answer(("pr", "merge"), "")

    await delivered.merge(shipping.id, by=OWNER)

    found = await tickets.get(shipping.id)
    assert found.merged
    assert found.pull_request == PullRequest(number=9, state=PullRequestState.MERGED, url=URL)
    assert (await stages.assess(shipping.id)).stage == "merged"
    assert fakes.caught_up == ["sample"]


async def test_a_pull_request_merged_on_github_is_recorded_on_its_next_read(
    delivered: DeliveryService,
    tickets: TicketService,
    shipping: Ticket,
    gh: ScriptedGh,
    clock: Clock,
) -> None:
    _ready(gh)
    await delivered.ship(shipping.id)
    gh.answer(("pr", "view"), pull_answer(state="MERGED"))
    clock.now += timedelta(seconds=61)

    await delivered.refresh_pulls()

    found = await tickets.get(shipping.id)
    assert found.pull_request == PullRequest(number=9, state=PullRequestState.MERGED, url=URL)
