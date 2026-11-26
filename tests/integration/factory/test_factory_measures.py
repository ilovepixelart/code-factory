"""The factory measures the board's own runs, costs and pull requests through the real services."""

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI

from code_factory.delivery.models import DeliveryEvent, PullReading
from code_factory.delivery.repository import DeliveryRepository
from code_factory.factory.service import FactoryService
from code_factory.platform.db import UnitOfWork
from code_factory.runs.models import Run
from code_factory.runs.repository import RunRepository
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService

URL = "https://github.com/o/r/pull/12"


async def test_a_costed_build_run_on_a_merged_pull_request_is_measured(
    app: FastAPI, uow: UnitOfWork
) -> None:
    services = app.state.services
    now = datetime.now(UTC)
    ticket = await services.get(TicketService).create(
        NewTicket(repository="sample", title="Audit log"), by="owner"
    )
    run = Run(
        id="r-measured", ticket_id=ticket.number, ticket_key=ticket.id, repository="sample",
        stage="build",
        started_at=now - timedelta(hours=2), ended_at=now - timedelta(hours=1), exit_code=0,
        cost=1.25, tokens=4000, agent="builder", model="opus",
    )  # fmt: skip
    async with uow() as session:
        await RunRepository(session).insert(run)
        delivery = DeliveryRepository(session)
        await delivery.record_pull(
            ticket.id, "sample", URL, PullReading(state="merged", ci="passed"), now
        )
        for kind, ago in (("pull_request", 50), ("merged_pull_request", 10)):
            await delivery.record(
                DeliveryEvent(
                    ticket_id=ticket.id, kind=kind, url=URL, at=now - timedelta(minutes=ago)
                )
            )

    board = await services.get(FactoryService).dashboard(
        (now - timedelta(days=7)).timestamp(), now.timestamp()
    )

    assert board.prs.model_dump()["merged"] == 1
    assert (board.cost.priced, board.cost.of, board.cost.median) == (1, 1, 1.25)
    assert {c.component: c.total for c in board.cost.by_component}["build"] == 1.25
    assert board.expensive[0].url == URL
