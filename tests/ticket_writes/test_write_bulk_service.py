"""One change to several cards, all or nothing, with one undo (G[40] to G[53])."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.stages.service import StageService
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.models import TicketFields
from code_factory.tickets.service import ActivityService, TicketService
from code_factory.undo.service import UndoService
from write_values import address, exactly, file

OWNER = "owner:owner"


async def entries(session: AsyncSession) -> int:
    return int(await session.scalar(text("select count(*) from undo_entries")) or 0)


async def test_a_priority_set_on_cards_of_two_repositories_is_one_undo(
    writes: TicketWriteService, tickets: TicketService, undo: UndoService
) -> None:
    one = await file(tickets, "One", priority="high")
    two = await file(tickets, "Two", "second", priority="medium")

    answer = await writes.bulk([address(one), address(two)], "priority", "low", OWNER)

    assert answer.notice == "Set low priority on 2 tickets"
    assert [(await tickets.get(t.id)).priority for t in (one, two)] == ["low", "low"]
    assert answer.undo is not None
    await undo.undo(answer.undo, OWNER)
    assert [(await tickets.get(t.id)).priority for t in (one, two)] == ["high", "medium"]


async def test_a_label_is_added_once_and_a_card_that_holds_it_is_untouched(
    writes: TicketWriteService, tickets: TicketService, activity: ActivityService
) -> None:
    plain = await file(tickets, "Plain", labels=["a"])
    held = await file(tickets, "Held", "second", labels=["ops"])

    answer = await writes.bulk([address(plain), address(held)], "label", "ops", OWNER)

    assert answer.notice == "Labelled 2 tickets ops"
    assert [(await tickets.get(t.id)).labels for t in (plain, held)] == [["a", "ops"], ["ops"]]
    changed = (await activity.list_activity(plain.id, kinds=["field"])).items
    assert [(r.data["name"], r.data["value"]) for r in changed] == [("labels", "a, ops")]
    assert (await activity.list_activity(held.id, kinds=["field"])).items == []


async def test_archiving_one_card_says_so_in_the_singular_and_undo_restores_it(
    writes: TicketWriteService, tickets: TicketService, undo: UndoService
) -> None:
    one = await file(tickets, "One")

    answer = await writes.bulk([address(one)], "archived", "true", OWNER)

    assert answer.notice == "Archived 1 ticket"
    assert (await tickets.get(one.id)).archived is True
    assert answer.undo is not None
    await undo.undo(answer.undo, OWNER)
    assert (await tickets.get(one.id)).archived is False
    restored = await writes.bulk([address(one)], "archived", "", OWNER)
    assert restored.notice == "Restored 1 ticket"


async def test_a_move_to_a_column_moves_every_card_and_one_undo_takes_them_back(
    writes: TicketWriteService, tickets: TicketService, stages: StageService, undo: UndoService
) -> None:
    first = await tickets.set_branch((await file(tickets, "First")).id, "feat/a", by=OWNER)
    second = await tickets.set_branch((await file(tickets, "Second")).id, "feat/b", by=OWNER)

    answer = await writes.bulk([address(first), address(second)], "stage", "spec", OWNER)

    assert answer.notice == "Moved 2 tickets to Spec"
    assert [(await stages.assess(t.id)).declared for t in (first, second)] == ["spec", "spec"]
    assert answer.undo is not None
    await undo.undo(answer.undo, OWNER)
    assert [(await stages.assess(t.id)).declared for t in (first, second)] == ["", ""]


async def test_a_bulk_that_changes_nothing_still_answers_its_notice_and_a_token(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    plain = await file(tickets, "Plain")
    low = await file(tickets, "Low", priority="low")

    moved = await writes.bulk([address(plain)], "stage", "spec", OWNER)
    same = await writes.bulk([address(low)], "priority", "low", OWNER)

    assert (moved.notice, moved.undo is not None) == ("Moved 1 ticket to Spec", True)
    assert (same.notice, same.undo is not None) == ("Set low priority on 1 ticket", True)


async def test_one_unknown_ticket_changes_none_and_offers_no_undo(
    writes: TicketWriteService, tickets: TicketService, db_session: AsyncSession
) -> None:
    one = await file(tickets, "One")
    gone = address(one).model_copy(update={"id": "CF-999999"})
    held = await entries(db_session)

    with pytest.raises(NotFoundError, match=exactly("no such ticket")):
        await writes.bulk([address(one), gone], "priority", "low", OWNER)

    assert (await tickets.get(one.id)).priority == ""
    assert await entries(db_session) == held


async def test_one_refused_column_move_changes_none_and_joins_every_refusal(
    writes: TicketWriteService, tickets: TicketService, stages: StageService
) -> None:
    first = await file(tickets, "First")
    second = await file(tickets, "Second")

    with pytest.raises(BadRequestError) as refused:
        await writes.bulk([address(first), address(second)], "stage", "build", OWNER)

    needs = "{id} needs a branch before Build: start an agent on it, or run code-factory start {id}"
    assert str(refused.value) == "; ".join(needs.format(id=t.id) for t in (first, second))
    assert [(await stages.assess(t.id)).declared for t in (first, second)] == ["", ""]


@pytest.mark.parametrize(
    ("field", "value", "sentence"),
    [
        ("stage", "later", "unknown stage later"),
        ("priority", "soon", "unknown priority soon"),
        ("label", "a, b", "a label is one word or phrase"),
        ("archived", "yes", "archived is true or empty"),
    ],
)
async def test_a_bulk_value_is_checked_before_any_ticket_is_looked_up(
    writes: TicketWriteService, tickets: TicketService, field: str, value: str, sentence: str
) -> None:
    one = await file(tickets, "One")
    gone = address(one).model_copy(update={"id": "CF-999999"})

    with pytest.raises(BadRequestError) as refused:
        await writes.bulk([gone], field, value, OWNER)

    assert str(refused.value) == sentence


async def test_a_request_body_names_one_action_and_its_cards(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    one = await file(tickets, "One")
    two = await file(tickets, "Two", "second")

    answer = await writes.bulk_request(
        {"tickets": [f"sample/{one.id}", f" second/{two.id} "], "priority": "low"}, OWNER
    )

    assert answer.notice == "Set low priority on 2 tickets"
    for body in (
        {"tickets": [f"sample/{one.id}"], "stage": "build", "priority": "low"},
        {"tickets": [], "priority": "low"},
    ):
        with pytest.raises(BadRequestError, match=exactly("one action and at least one ticket")):
            await writes.bulk_request(body, OWNER)


async def test_a_card_named_twice_is_changed_and_counted_once(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    one = await file(tickets, "One")

    answer = await writes.bulk([address(one), address(one)], "priority", "low", OWNER)

    assert answer.notice == "Set low priority on 1 ticket"


async def test_a_card_the_bulk_left_as_it_was_does_not_block_its_undo(
    writes: TicketWriteService, tickets: TicketService, undo: UndoService
) -> None:
    changed = await file(tickets, "Changed", labels=["a"])
    held = await file(tickets, "Held", labels=["ops"])
    answer = await writes.bulk([address(changed), address(held)], "label", "ops", OWNER)
    assert answer.undo is not None
    await tickets.update(held.id, TicketFields(labels=["other"]), by="agent:run-1")

    await undo.undo(answer.undo, OWNER)

    assert (await tickets.get(changed.id)).labels == ["a"]
    assert (await tickets.get(held.id)).labels == ["other"]


async def test_a_bulk_on_a_field_that_is_no_action_renames_nothing(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    one = await file(tickets, "One")

    with pytest.raises(BadRequestError, match=exactly("one action and at least one ticket")):
        await writes.bulk([address(one)], "title", "Renamed", OWNER)

    assert (await tickets.get(one.id)).title == "One"


async def test_a_label_given_padded_is_stored_trimmed_and_its_undo_applies(
    writes: TicketWriteService, tickets: TicketService, undo: UndoService
) -> None:
    one = await file(tickets, "One")
    answer = await writes.bulk([address(one)], "label", " ops ", OWNER)
    assert answer.undo is not None
    assert (await tickets.get(one.id)).labels == ["ops"]

    await undo.undo(answer.undo, OWNER)

    assert (await tickets.get(one.id)).labels == []
