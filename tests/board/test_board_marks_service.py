"""An edit moves neither the column entry time nor the archive date: they come from the history."""

import json
from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi import FastAPI

from code_factory.board.module import board_sources
from code_factory.board.service import BoardService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.services import Services
from code_factory.tickets.models import NewActivity, NewTicket, TicketFields
from code_factory.tickets.service import ActivityService, TicketService

NOW = datetime(2026, 11, 30, 12, 0, tzinfo=UTC)
ENTERED = datetime(2026, 11, 24, 8, 0, tzinfo=UTC)
EDITED = datetime(2026, 11, 29, 8, 0, tzinfo=UTC)


@pytest.fixture
def desk(app: FastAPI, uow: UnitOfWork) -> BoardService:
    return BoardService(board_sources(cast("Services", app.state.services)), uow, clock=lambda: NOW)


async def test_editing_a_ticket_keeps_the_time_it_entered_its_column(
    desk: BoardService, uow: UnitOfWork, activity: ActivityService
) -> None:
    tickets = TicketService(uow, clock=lambda: EDITED)
    made = await tickets.create(NewTicket(repository="sample", title="A ticket"), by="alex")
    await activity.append(
        made.id, NewActivity(kind="stage", data={"to": "spec"}, at=ENTERED), by="alex"
    )
    await tickets.update(made.id, TicketFields(title="typo fixed"), by="alex")
    card = await desk.ticket_card("sample", made.id)
    assert card is not None
    assert (card["stage_since"], card["days_in_column"]) == ("2026-11-24T08:00:00Z", 6)
    page = await desk.ticket_page("sample", made.id)
    assert page["ticket"]["stage_since"] == "2026-11-24T08:00:00Z"


async def test_editing_an_archived_ticket_keeps_the_date_it_was_archived(
    desk: BoardService, uow: UnitOfWork
) -> None:
    archived_at = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    made = await TicketService(uow, clock=lambda: archived_at).create(
        NewTicket(repository="sample", title="Old"), by="alex"
    )
    await TicketService(uow, clock=lambda: archived_at).archive(made.id, by="alex")
    await TicketService(uow, clock=lambda: EDITED).update(
        made.id, TicketFields(title="renamed in archive"), by="alex"
    )
    rows = json.loads(json.dumps(await desk.archive({"q": made.id})))["rows"]
    assert [(r["id"], r["archived_at"]) for r in rows] == [(made.id, archived_at.timestamp())]
