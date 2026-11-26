"""The unit sets a ticket's archived flag and branch in its own transaction (ticket-writes)."""

import pytest

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.tickets.models import (
    Column,
    NewTicket,
    TicketAddress,
    TicketFields,
    TicketFilter,
)
from code_factory.tickets.service import ActivityService, TicketService
from ticket_values import OWNER

REPO = "unit-facts"
WAIT = 1.0


async def make(tickets: TicketService, title: str) -> TicketAddress:
    made = await tickets.create(NewTicket(repository=REPO, title=title), by=OWNER)
    return TicketAddress(repository=REPO, id=made.id)


async def test_set_archived_takes_the_ticket_off_the_board_and_says_whether_it_changed(
    tickets: TicketService, activity: ActivityService
) -> None:
    one = await make(tickets, "One")
    async with tickets.unit([REPO], wait=WAIT) as unit:
        assert await unit.set_archived(one, archived=True) is True
        assert await unit.set_archived(one, archived=True) is False
    assert await tickets.list(TicketFilter(repository=REPO)) == []
    assert (await tickets.get(one.id)).archived is True
    assert [r.kind for r in (await activity.list_activity(one.id)).items] == ["created"]
    async with tickets.unit([REPO], wait=WAIT) as unit:
        assert await unit.set_archived(one, archived=False) is True
    assert [t.id for t in await tickets.list(TicketFilter(repository=REPO))] == [one.id]


async def test_set_branch_puts_the_ticket_in_build_and_an_empty_name_takes_it_out(
    tickets: TicketService,
) -> None:
    one = await make(tickets, "One")
    async with tickets.unit([REPO], wait=WAIT) as unit:
        assert await unit.set_branch(one, "feat/one") is True
        assert await unit.set_branch(one, "feat/one") is False
    held = await tickets.get(one.id)
    assert (held.branch, held.column) == ("feat/one", Column.BUILD)
    async with tickets.unit([REPO], wait=WAIT) as unit:
        assert await unit.set_branch(one, "") is True
    assert (await tickets.get(one.id)).column is Column.SPEC


async def test_a_flag_or_branch_of_a_missing_ticket_is_not_found(tickets: TicketService) -> None:
    missing = TicketAddress(repository=REPO, id="CF-999999")
    async with tickets.unit([REPO], wait=WAIT) as unit:
        with pytest.raises(NotFoundError, match="CF-999999"):
            await unit.set_archived(missing, archived=True)
        with pytest.raises(NotFoundError, match="CF-999999"):
            await unit.set_branch(missing, "x")


async def test_a_flag_set_in_a_unit_that_raises_is_not_kept(tickets: TicketService) -> None:
    one = await make(tickets, "One")

    async def stopped() -> None:
        async with tickets.unit([REPO], wait=WAIT) as unit:
            await unit.set_archived(one, archived=True)
            await unit.set_branch(one, "feat/one")
            raise RuntimeError("stop")

    with pytest.raises(RuntimeError, match="stop"):
        await stopped()
    kept = await tickets.get(one.id)
    assert (kept.archived, kept.branch) == (False, "")


async def test_a_list_of_links_can_change_while_it_still_names_a_ticket_that_was_deleted(
    tickets: TicketService,
) -> None:
    gone = await make(tickets, "Gone")
    kept = await make(tickets, "Kept")
    held = await tickets.create(
        NewTicket(repository=REPO, title="Held", blocked_by=[gone.id, kept.id]), by=OWNER
    )
    async with tickets.unit([REPO], wait=WAIT) as unit:
        await unit.trash(gone)

    await tickets.update(held.id, TicketFields(blocked_by=[gone.id]), by=OWNER)

    assert (await tickets.get(held.id)).blocked_by == [gone.id]
    with pytest.raises(BadRequestError, match=f"{gone.id} does not exist"):
        await tickets.update(held.id, TicketFields(caused_by=[gone.id]), by=OWNER)
