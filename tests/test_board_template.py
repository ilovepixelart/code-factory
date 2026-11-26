"""The `board_ids` fixture hands each test the `board` sample as `SampleService.load` leaves it."""

import os
import re

from code_factory.sample.models import BOARD_TICKETS
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService
from ticket_values import OWNER


async def test_a_ticket_made_after_the_sample_takes_a_number_no_sample_ticket_has(
    tickets: TicketService, board_ids: dict[str, str]
) -> None:
    made = await tickets.create(NewTicket(repository="sample", title="After the sample"), by=OWNER)
    assert made.id not in board_ids.values()


async def test_the_board_sample_holds_exactly_the_tickets_the_sample_lists(
    tickets: TicketService, board_ids: dict[str, str]
) -> None:
    held = {ticket.id for ticket in await tickets.list()}
    live = {board_ids[spec["title"]] for spec in BOARD_TICKETS if not spec.get("archived")}
    assert len(board_ids) == len(BOARD_TICKETS)
    assert held == live


def test_an_xdist_worker_runs_in_a_schema_of_its_own() -> None:
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker is None:
        return
    assert re.fullmatch(rf"test_[0-9a-f]{{32}}_{worker}", os.environ["CODE_FACTORY_DB_SCHEMA"])
