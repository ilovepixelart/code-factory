"""Dragging a card: the column through the stages module, then the order (G[28] to G[34])."""

import pytest

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.stages.models import MoveRefusedError
from code_factory.stages.service import StageService
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.models import Ticket, TicketFields
from code_factory.tickets.service import ActivityService, TicketService
from code_factory.undo.service import UndoService
from write_values import address, exactly, file

OWNER = "owner:owner"


async def built(tickets: TicketService, title: str, repository: str = "sample") -> Ticket:
    """A ticket with a branch: the evidence puts it in Build."""
    made = await file(tickets, title, repository)
    return await tickets.set_branch(made.id, f"feat/{made.id.lower()}", by=OWNER)


async def ranks(tickets: TicketService, *tickets_: Ticket) -> list[int]:
    return [(await tickets.get(t.id)).rank for t in tickets_]


async def test_a_move_back_declares_the_column_numbers_the_drop_and_offers_one_undo(
    writes: TicketWriteService, tickets: TicketService, stages: StageService
) -> None:
    moved = await built(tickets, "Declared")
    other = await file(tickets, "Other")
    elsewhere = await file(tickets, "Elsewhere", "second")
    await tickets.update(other.id, TicketFields(rank=2), by=OWNER)

    answer = await writes.move(
        address(moved),
        "spec",
        [f"sample/{moved.id}", f"sample/{other.id}", f"second/{elsewhere.id}"],
        OWNER,
    )

    assert (answer.notice, answer.undo is not None) == (f"Moved {moved.id} to Spec", True)
    assert (await stages.assess(moved.id)).declared == "spec"
    assert await ranks(tickets, moved, other, elsewhere) == [1, 2, 1]


async def test_a_rank_that_does_not_change_is_not_written_and_ranks_are_not_activity(
    writes: TicketWriteService, tickets: TicketService, activity: ActivityService
) -> None:
    first = await built(tickets, "First")
    second = await file(tickets, "Second")
    await tickets.update(second.id, TicketFields(rank=2), by=OWNER)
    before = len((await activity.list_activity(second.id)).items)
    first_before = len((await activity.list_activity(first.id)).items)

    await writes.move(address(first), "spec", [f"sample/{first.id}", f"sample/{second.id}"], OWNER)

    assert len((await activity.list_activity(second.id)).items) == before
    kinds = [r.kind for r in (await activity.list_activity(first.id)).items]
    assert (len(kinds), kinds[-1]) == (first_before + 1, "stage")


async def test_undoing_a_move_puts_back_the_column_and_the_ranks(
    writes: TicketWriteService, tickets: TicketService, stages: StageService, undo: UndoService
) -> None:
    moved = await built(tickets, "Declared")
    other = await file(tickets, "Other")
    answer = await writes.move(
        address(moved), "spec", [f"sample/{other.id}", f"sample/{moved.id}"], OWNER
    )
    assert answer.undo is not None

    await undo.undo(answer.undo, OWNER)

    assert (await stages.assess(moved.id)).declared == ""
    assert await ranks(tickets, moved, other) == [0, 0]


async def test_a_move_into_the_column_already_declared_only_reorders(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    held = await built(tickets, "Held")
    other = await file(tickets, "Other")
    await writes.move(address(held), "spec", [], OWNER)

    again = await writes.move(
        address(held), "spec", [f"sample/{other.id}", f"sample/{held.id}"], OWNER
    )

    assert (again.notice, again.undo) == ("", None)
    assert await ranks(tickets, other, held) == [1, 2]


async def test_a_drop_on_the_column_the_evidence_reached_offers_no_undo(
    writes: TicketWriteService, tickets: TicketService, stages: StageService
) -> None:
    plain = await file(tickets, "Plain")

    answer = await writes.move(address(plain), "spec", [f"sample/{plain.id}"], OWNER)

    assert (answer.notice, answer.undo) == ("", None)
    assert (await stages.assess(plain.id)).declared == ""
    assert (await tickets.get(plain.id)).rank == 1


@pytest.mark.parametrize(
    ("stage", "sentence"),
    [
        (
            "build",
            (
                "{id} needs a branch before Build: start an agent on it, "
                "or run code-factory start {id}"
            ),
        ),
        ("review", "{id} moves one column at a time: Build is next"),
    ],
)
async def test_a_move_the_board_refuses_passes_its_sentence_and_changes_no_rank(
    writes: TicketWriteService, tickets: TicketService, stage: str, sentence: str
) -> None:
    plain = await file(tickets, "Plain")

    with pytest.raises(MoveRefusedError) as refused:
        await writes.move(address(plain), stage, [f"sample/{plain.id}"], OWNER)

    assert str(refused.value) == sentence.format(id=plain.id)
    assert (await tickets.get(plain.id)).rank == 0


async def test_a_move_of_a_missing_ticket_or_to_an_unknown_column_is_refused(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    plain = await file(tickets, "Plain")
    with pytest.raises(NotFoundError, match=exactly("no such ticket")):
        await writes.move(address(plain).model_copy(update={"id": "CF-999999"}), "spec", [], OWNER)
    with pytest.raises(BadRequestError, match=exactly("unknown stage later")):
        await writes.move(address(plain), "later", [f"sample/{plain.id}"], OWNER)
    assert (await tickets.get(plain.id)).rank == 0


async def test_drop_entries_that_name_no_ticket_are_skipped_without_a_word(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    held = await built(tickets, "Held")

    answer = await writes.move(
        address(held),
        "spec",
        ["nowhere/CF-1", "sample/CF-999999", "sample/garbage", "lonely", "", f"sample/{held.id}"],
        OWNER,
    )

    assert answer.undo is not None
    assert (await tickets.get(held.id)).rank == 3  # third of the sample entries
