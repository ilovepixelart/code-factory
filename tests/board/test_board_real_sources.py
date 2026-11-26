"""The board of the composed app reads the real runs, checks, pull requests and column limits."""

import json
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.board.service import BoardService
from code_factory.delivery.models import DeliveryEvent, PullReading
from code_factory.delivery.repository import DeliveryRepository
from code_factory.platform.services import Services
from code_factory.runs.repository import RunRepository
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.models import NewTicket, Ticket
from code_factory.tickets.service import TicketService
from runs_values import a_run, at
from ticket_values import OWNER

HEAD = "a" * 40
URL = "https://github.com/o/r/pull/7"
READ_AT = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


@pytest.fixture
def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


@pytest.fixture
async def wired(services: Services) -> Ticket:
    """A ticket of `sample` made through the app's own ticket service."""
    tickets = services.get(TicketService)
    return await tickets.create(NewTicket(repository="sample", title="Wired"), by=OWNER)


async def card_of(services: Services, ticket: Ticket) -> dict[str, Any]:
    card = await services.get(BoardService).ticket_card("sample", ticket.id)
    assert card is not None
    return card


async def test_the_card_spends_what_its_runs_cost_and_lists_the_active_one(
    services: Services, db_session: AsyncSession, wired: Ticket
) -> None:
    repo = RunRepository(db_session)
    number = wired.number
    await repo.insert(a_run(number, "ended", exit_code=0, ended_at=at(60), cost=1.25))
    await repo.insert(a_run(number, "review", stage="review", exit_code=0, cost=0.5))
    await repo.insert(a_run(number, "active", started_at=at(120), iteration=2, looping=True))

    card = await card_of(services, wired)

    assert card["spent"] == 1.75
    assert [(r["id"], r["iteration"], r["loop"], r["max_iterations"]) for r in card["runs"]] == [
        ("active", 2, True, 12)
    ]


async def test_the_card_shows_the_check_its_checks_recorded(
    services: Services, wired: Ticket
) -> None:
    data: dict[str, object] = {"commit": HEAD, "exit_code": 0}
    await services.get(TicketService).record_activity(wired.id, "checks", data, by="board")

    card = await card_of(services, wired)

    assert card["check"] == {"passed": True, "commit": HEAD}


async def test_the_card_shows_the_pull_request_delivery_recorded(
    services: Services, db_session: AsyncSession, wired: Ticket
) -> None:
    reading = PullReading(state="open", review="approved", ci="passed", head=HEAD, base="main")
    await DeliveryRepository(db_session).record_pull(wired.id, "sample", URL, reading, READ_AT)

    card = await card_of(services, wired)

    assert card["pull"] == {
        "state": "open", "review": "approved", "ci": "passed", "head": HEAD, "url": URL,
        "at": str(READ_AT.timestamp()), "since": str(READ_AT.timestamp()),
    }  # fmt: skip


async def test_the_card_shows_where_delivery_stands(
    services: Services, db_session: AsyncSession, wired: Ticket
) -> None:
    retry = datetime(2026, 11, 23, 13, 0, tzinfo=UTC)
    failed = DeliveryEvent(
        ticket_id=wired.id, kind="ship_failed", head=HEAD, reason="no", retry_at=retry, at=READ_AT
    )
    await DeliveryRepository(db_session).record(failed)

    card = await card_of(services, wired)

    assert card["delivery_event"] == {
        "kind": "ship_failed",
        "at": READ_AT.timestamp(),
        "retry_at": retry.timestamp(),
        "reason": "no",
    }


async def test_the_board_carries_the_column_limits_the_owner_set(services: Services) -> None:
    await services.get(TicketWriteService).set_column_limit("build", 3, by=OWNER)

    board = json.loads((await services.get(BoardService).board()).body)

    assert board["limits"] == {"build": 3}
