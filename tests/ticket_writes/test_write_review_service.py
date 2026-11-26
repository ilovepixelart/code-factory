"""Behaviours an independent review found missing: empty column, huge ids, undo atomicity."""

from typing import Any

import pytest

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.stages.service import StageService
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.models import TicketAddress
from code_factory.tickets.service import TicketService
from code_factory.undo.service import UndoService
from write_values import address, exactly, file

OWNER = "owner:owner"
OTHER = "agent:run-1"
HUGE = "CF-99999999999999999999"


async def built(tickets: TicketService, title: str) -> Any:  # noqa: ANN401  # a ticket
    made = await file(tickets, title)
    return await tickets.set_branch(made.id, f"feat/{made.id.lower()}", by=OWNER)


async def test_a_move_to_an_empty_column_clears_the_declaration_and_offers_no_undo(
    writes: TicketWriteService, tickets: TicketService, stages: StageService
) -> None:
    held = await built(tickets, "Held")
    other = await file(tickets, "Other")
    await stages.declare(held.id, "spec", OWNER)

    answer = await writes.move(
        address(held), "", [f"sample/{other.id}", f"sample/{held.id}"], OWNER
    )

    assert (answer.notice, answer.undo) == ("", None)
    assert (await stages.assess(held.id)).declared == ""
    assert [(await tickets.get(t.id)).rank for t in (other, held)] == [1, 2]


async def test_a_ticket_number_beyond_the_database_is_no_ticket_to_move_edit_or_link(
    writes: TicketWriteService, tickets: TicketService, stages: StageService
) -> None:
    held = await built(tickets, "Held")
    ref = address(held)
    gone = TicketAddress(repository="sample", id=HUGE)

    answer = await writes.move(ref, "spec", [f"sample/{HUGE}", f"sample/{held.id}"], OWNER)

    assert answer.undo is not None
    assert (await stages.assess(held.id)).declared == "spec"
    with pytest.raises(NotFoundError, match=exactly("no such ticket")):
        await writes.update(gone, {"title": "x"}, OWNER)
    for kind in ("blocks", "blocked_by"):
        with pytest.raises(BadRequestError, match=exactly(f"no ticket {HUGE}")):
            await writes.add_link(ref, kind, HUGE, OWNER)


async def test_an_undo_whose_column_changes_after_the_guard_is_refused_and_writes_nothing(
    writes: TicketWriteService,
    tickets: TicketService,
    stages: StageService,
    undo: UndoService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = await built(tickets, "Held")
    answer = await writes.move(address(held), "spec", [], OWNER)
    assert answer.undo is not None
    declare = stages.declare

    async def raced(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401  # the real call's shape
        monkeypatch.setattr(stages, "declare", declare)
        await declare(held.id, "review", OTHER)
        return await declare(*args, **kwargs)

    monkeypatch.setattr(stages, "declare", raced)

    with pytest.raises(ConflictError) as refused:
        await undo.undo(answer.undo, OWNER)

    assert str(refused.value) == (
        f"{held.id} stage changed since: it is review now, not spec as the change left it"
    )
    assert (await stages.assess(held.id)).declared == "review"


async def test_an_undo_that_loses_the_race_on_a_second_column_puts_the_first_back(
    writes: TicketWriteService,
    tickets: TicketService,
    stages: StageService,
    undo: UndoService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = await built(tickets, "First")
    second = await built(tickets, "Second")
    answer = await writes.bulk([address(first), address(second)], "stage", "spec", OWNER)
    assert answer.undo is not None
    declare = stages.declare

    async def raced(ticket: str, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401  # as declare
        if ticket == second.id:
            monkeypatch.setattr(stages, "declare", declare)
            await declare(second.id, "review", OTHER)
        return await declare(ticket, *args, **kwargs)

    monkeypatch.setattr(stages, "declare", raced)

    with pytest.raises(ConflictError):
        await undo.undo(answer.undo, OWNER)

    assert [(await stages.assess(t.id)).declared for t in (first, second)] == ["spec", "review"]


async def test_an_undo_whose_fields_are_refused_puts_the_column_back(
    writes: TicketWriteService, tickets: TicketService, stages: StageService, undo: UndoService
) -> None:
    held = await built(tickets, "Held")
    other = await file(tickets, "Other", priority="low")
    moved = await writes.move(address(held), "spec", [], OWNER)
    assert moved.undo is not None
    stored = await writes._undo.offer(  # a payload mixing a column and a field
        "tickets.revert",
        {
            "ops": [
                {"op": "stage", "id": held.id, "to": "", "expect": {"stage": "spec"}},
                {
                    "op": "fields",
                    "repository": "sample",
                    "id": other.id,
                    "to": {"priority": ""},
                    "expect": {"priority": "high"},
                },
            ]
        },
        "n",
    )
    assert stored.undo is not None

    with pytest.raises(ConflictError, match=f"{other.id} priority changed since"):
        await undo.undo(stored.undo, OWNER)

    assert (await stages.assess(held.id)).declared == "spec"


async def test_a_card_the_bulk_column_move_left_as_it_was_does_not_block_its_undo(
    writes: TicketWriteService, tickets: TicketService, stages: StageService, undo: UndoService
) -> None:
    changed = await built(tickets, "Changed")
    held = await built(tickets, "Held")
    await stages.declare(held.id, "spec", OWNER)
    answer = await writes.bulk([address(changed), address(held)], "stage", "spec", OWNER)
    assert answer.undo is not None
    await stages.declare(held.id, "build", OTHER)

    await undo.undo(answer.undo, OWNER)

    assert [(await stages.assess(t.id)).declared for t in (changed, held)] == ["", "build"]


async def test_an_edit_names_the_column_as_changed_only_when_the_declaration_changed(
    writes: TicketWriteService, tickets: TicketService, stages: StageService
) -> None:
    one = await file(tickets, "Plain")
    await stages.declare(one.id, "spec", OWNER)

    same = await writes.update(address(one), {"stage": "spec"}, OWNER)

    assert same.changed == []


async def test_a_parent_names_one_ticket_and_a_list_is_refused_as_no_such_ticket(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    one = await file(tickets, "One")
    two = await file(tickets, "Two")
    child = await file(tickets, "Child")

    with pytest.raises(BadRequestError, match=exactly(f"no ticket {one.id}, {two.id}")):
        await writes.update(address(child), {"parent": f"{one.id}, {two.id}"}, OWNER)

    assert (await tickets.get(child.id)).parent == ""


async def test_a_bulk_of_no_tickets_is_refused_for_every_caller(
    writes: TicketWriteService,
) -> None:
    with pytest.raises(BadRequestError, match=exactly("one action and at least one ticket")):
        await writes.bulk([], "priority", "low", OWNER)
