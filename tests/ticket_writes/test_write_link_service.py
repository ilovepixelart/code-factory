"""Adding and removing a link by kind (previous `links.rs`, G[15] to G[17])."""

import pytest

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.models import Ticket
from code_factory.tickets.service import TicketService
from code_factory.undo.service import UndoService
from write_values import address, exactly, file

OWNER = "owner:owner"


def held(ticket: Ticket, field: str) -> str:
    value: object = getattr(ticket, field)
    return ", ".join(map(str, value)) if isinstance(value, list) else str(value)


@pytest.mark.parametrize(
    ("kind", "target_holds", "field"),
    [("parent", False, "parent"), ("child", True, "parent"),
     ("blocked_by", False, "blocked_by"), ("blocks", True, "blocked_by")],
)  # fmt: skip
async def test_each_kind_is_written_on_the_ticket_that_holds_it_and_removed_back_to_empty(
    writes: TicketWriteService, tickets: TicketService, kind: str, target_holds: bool, field: str
) -> None:
    own = await file(tickets, "Own")
    other = await file(tickets, "Other")
    holder, value = (other, own.id) if target_holds else (own, other.id)

    added = await writes.add_link(address(own), kind, other.id, OWNER)
    after_add = held(await tickets.get(holder.id), field)
    removed = await writes.remove_link(address(own), kind, other.id, OWNER)

    verb = kind.replace("_", " ")
    assert added.notice == f"Linked {other.id} as {verb} of {own.id}"
    assert removed.notice == f"Unlinked {other.id} as {verb} of {own.id}"
    assert (after_add, held(await tickets.get(holder.id), field)) == (value, "")


async def test_a_blocker_is_added_to_the_ones_held_and_removed_singly(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    first = await file(tickets, "First")
    second = await file(tickets, "Second")
    own = await file(tickets, "Own", blocked_by=[first.id])

    await writes.add_link(address(own), "blocked_by", second.id, OWNER)
    assert (await tickets.get(own.id)).blocked_by == [first.id, second.id]
    await writes.remove_link(address(own), "blocked_by", first.id, OWNER)
    assert (await tickets.get(own.id)).blocked_by == [second.id]


async def test_undoing_a_link_puts_the_holder_s_field_back(
    writes: TicketWriteService, tickets: TicketService, undo: UndoService
) -> None:
    own = await file(tickets, "Own")
    other = await file(tickets, "Other")
    added = await writes.add_link(address(own), "blocks", other.id, OWNER)
    assert added.undo is not None

    await undo.undo(added.undo, OWNER)

    assert (await tickets.get(other.id)).blocked_by == []


async def test_a_link_that_makes_a_loop_is_refused_and_leaves_both_tickets_alone(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    top = await file(tickets, "Top")
    low = await file(tickets, "Low")
    await writes.add_link(address(top), "parent", low.id, OWNER)

    with pytest.raises(BadRequestError, match=exactly(f"parent {top.id} would make a loop")):
        await writes.add_link(address(top), "child", low.id, OWNER)

    assert (await tickets.get(top.id)).parent == low.id
    assert (await tickets.get(low.id)).parent == ""


@pytest.mark.parametrize("kind", ["parent", "blocked_by"])
async def test_a_target_that_is_not_there_is_refused(
    writes: TicketWriteService, tickets: TicketService, kind: str
) -> None:
    own = await file(tickets, "Own")

    with pytest.raises(BadRequestError, match=exactly("no ticket CF-999999")):
        await writes.add_link(address(own), kind, "CF-999999", OWNER)


@pytest.mark.parametrize("kind", ["child", "blocks"])
async def test_a_target_that_would_hold_the_link_must_exist_in_the_repository(
    writes: TicketWriteService, tickets: TicketService, kind: str
) -> None:
    own = await file(tickets, "Own")
    foreign = await file(tickets, "Foreign", "second")

    for target in ("CF-999999", foreign.id, "nonsense"):
        with pytest.raises(BadRequestError, match=exactly(f"no ticket {target}")):
            await writes.add_link(address(own), kind, target, OWNER)


async def test_a_ticket_cannot_be_linked_to_itself(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    own = await file(tickets, "Own")

    with pytest.raises(BadRequestError, match=exactly(f"{own.id} cannot link to itself")):
        await writes.add_link(address(own), "blocked_by", own.id, OWNER)


async def test_removing_a_link_that_is_not_there_names_both_tickets(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    own = await file(tickets, "Own")
    other = await file(tickets, "Other")

    with pytest.raises(BadRequestError) as refused:
        await writes.remove_link(address(own), "parent", other.id, OWNER)

    assert str(refused.value) == f"{other.id} is not linked to {own.id} that way"


async def test_an_unknown_kind_and_an_unknown_own_ticket_are_refused(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    own = await file(tickets, "Own")
    with pytest.raises(BadRequestError, match=exactly("unknown link kind sibling")):
        await writes.add_link(address(own), "sibling", own.id, OWNER)
    given = address(own).model_copy(update={"id": "CF-999999"})
    with pytest.raises(NotFoundError, match=exactly("no such ticket")):
        await writes.add_link(given, "parent", own.id, OWNER)
