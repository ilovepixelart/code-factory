"""A coordinator's edit of a ticket and putting it back.

Oracles are the previous implementation's coordinator-undo answers: the put-back notice
`Put priority back to low`, the 404 `the coordinator made no edit of priority on CF-1`, and the
409 `priority changed since: it is urgent now, not high as the coordinator left it`.
"""

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.tickets.models import Edited, NewTicket, Ticket, TicketFields
from code_factory.tickets.service import ActivityService, CoordinatorService, TicketService
from code_factory.undo.service import UndoService
from ticket_values import OWNER

COORDINATOR = "coordinator"


@pytest.fixture
def undo(uow: UnitOfWork) -> UndoService:
    return UndoService(uow)


@pytest.fixture
def coordinator(tickets: TicketService, undo: UndoService) -> CoordinatorService:
    return CoordinatorService(tickets, undo)


@pytest.fixture
async def low(tickets: TicketService) -> Ticket:
    return await tickets.create(
        NewTicket(repository="sample", title="One", priority="low"), by=OWNER
    )


async def test_an_edit_records_each_changed_field_as_the_coordinators(
    coordinator: CoordinatorService, activity: ActivityService, low: Ticket
) -> None:
    changed = await coordinator.edit(low.id, TicketFields(priority="high", rank=3), by=COORDINATOR)
    assert changed.undo is not None
    records = (await activity.list_activity(low.id, kinds=["coordinator_edit"])).items
    assert [(r.by, r.data) for r in records] == [
        (COORDINATOR, {"name": "priority", "from": "low", "to": "high"}),
        (COORDINATOR, {"name": "rank", "from": 0, "to": 3}),
    ]


async def test_an_edit_that_changes_nothing_offers_no_undo(
    coordinator: CoordinatorService, activity: ActivityService, low: Ticket
) -> None:
    changed = await coordinator.edit(low.id, TicketFields(priority="low"), by=COORDINATOR)
    assert (changed.notice, changed.undo) == (f"Nothing changed on {low.id}", None)
    assert (await activity.list_activity(low.id, kinds=["coordinator_edit"])).items == []


async def test_the_coordinator_may_set_only_four_fields(
    coordinator: CoordinatorService, tickets: TicketService, low: Ticket
) -> None:
    with pytest.raises(BadRequestError, match="only priority, labels, blocked_by and rank"):
        await coordinator.edit(low.id, TicketFields(priority="high", title="New"), by=COORDINATOR)
    assert (await tickets.get(low.id)).priority == "low"


async def test_the_token_of_an_edit_puts_every_field_back(
    coordinator: CoordinatorService, undo: UndoService, tickets: TicketService, low: Ticket
) -> None:
    other = await tickets.create(NewTicket(repository="sample", title="Two"), by=OWNER)
    fields = TicketFields(priority="high", labels=["a", "b"], blocked_by=[other.id], rank=3)
    changed = await coordinator.edit(low.id, fields, by=COORDINATOR)
    assert changed.undo is not None
    await undo.undo(changed.undo, OWNER)
    back = await tickets.get(low.id)
    assert (back.priority, back.labels, back.blocked_by, back.rank) == ("low", [], [], 0)


async def test_one_field_is_put_back_by_name_as_the_owners_edit(
    coordinator: CoordinatorService, activity: ActivityService, tickets: TicketService, low: Ticket
) -> None:
    await coordinator.edit(low.id, TicketFields(priority="high"), by=COORDINATOR)
    answer = await coordinator.undo_edit(low.id, "priority", by=OWNER)
    assert (answer.notice, answer.undo) == ("Put priority back to low", None)
    assert (await tickets.get(low.id)).priority == "low"
    edits = (await activity.list_activity(low.id, kinds=["edited"], newest_first=True)).items
    assert (edits[0].by, edits[0].data) == (OWNER, {"fields": ["priority"]})


async def test_a_field_with_no_coordinator_edit_is_not_found(
    coordinator: CoordinatorService, low: Ticket
) -> None:
    with pytest.raises(
        NotFoundError, match=f"the coordinator made no edit of priority on {low.id}"
    ):
        await coordinator.undo_edit(low.id, "priority", by=OWNER)


async def test_a_field_changed_since_is_refused_and_left_alone(
    coordinator: CoordinatorService, tickets: TicketService, low: Ticket
) -> None:
    await coordinator.edit(low.id, TicketFields(priority="high"), by=COORDINATOR)
    await tickets.update(low.id, TicketFields(priority="urgent"), by=OWNER)
    with pytest.raises(
        ConflictError,
        match="priority changed since: it is urgent now, not high as the coordinator left it",
    ):
        await coordinator.undo_edit(low.id, "priority", by=OWNER)
    assert (await tickets.get(low.id)).priority == "urgent"


async def test_only_the_four_fields_can_be_put_back(
    coordinator: CoordinatorService, low: Ticket
) -> None:
    with pytest.raises(BadRequestError, match="only priority, labels, blocked_by and rank"):
        await coordinator.undo_edit(low.id, "title", by=OWNER)


async def test_a_label_with_a_comma_is_put_back_whole(
    coordinator: CoordinatorService, tickets: TicketService, low: Ticket
) -> None:
    await tickets.update(low.id, TicketFields(labels=["old"]), by=OWNER)
    changed = await coordinator.edit(low.id, TicketFields(labels=["UI, mobile"]), by=COORDINATOR)
    assert changed.undo is not None
    await coordinator.undo_edit(low.id, "labels", by=OWNER)
    assert (await tickets.get(low.id)).labels == ["old"]


async def test_labels_that_only_print_alike_are_a_change_since(
    coordinator: CoordinatorService, tickets: TicketService, low: Ticket
) -> None:
    await coordinator.edit(low.id, TicketFields(labels=["a, b"]), by=COORDINATOR)
    await tickets.update(low.id, TicketFields(labels=["a", "b"]), by=OWNER)
    with pytest.raises(ConflictError, match="labels changed since"):
        await coordinator.undo_edit(low.id, "labels", by=OWNER)
    assert (await tickets.get(low.id)).labels == ["a", "b"]


async def test_an_earlier_token_does_not_undo_a_later_edit(
    coordinator: CoordinatorService, undo: UndoService, tickets: TicketService, low: Ticket
) -> None:
    first = await coordinator.edit(low.id, TicketFields(priority="high"), by=COORDINATOR)
    second = await coordinator.edit(low.id, TicketFields(priority="urgent"), by=COORDINATOR)
    assert first.undo is not None
    assert second.undo is not None
    with pytest.raises(ConflictError, match="priority changed since: it is urgent now, not high"):
        await undo.undo(first.undo, OWNER)
    assert (await tickets.get(low.id)).priority == "urgent"
    await undo.undo(second.undo, OWNER)
    assert (await tickets.get(low.id)).priority == "high"


async def test_a_hand_appended_coordinator_edit_cannot_steer_the_undo(
    coordinator: CoordinatorService, tickets: TicketService, low: Ticket
) -> None:
    with pytest.raises(BadRequestError, match="coordinator_edit is written by"):
        await tickets.record_activity(
            low.id, "coordinator_edit", {"name": "priority", "from": "urgent", "to": "low"}, by="x"
        )
    with pytest.raises(NotFoundError, match="the coordinator made no edit of priority"):
        await coordinator.undo_edit(low.id, "priority", by=OWNER)


async def test_the_token_undoes_the_edit_it_was_offered_for_not_a_later_one(
    coordinator: CoordinatorService,
    undo: UndoService,
    tickets: TicketService,
    low: Ticket,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = tickets.update

    async def another_edit_lands_first(
        ticket: str, fields: TicketFields, *, by: str, coordinator: bool = False
    ) -> Edited:
        edited = await update(ticket, fields, by=by, coordinator=coordinator)
        await update(low.id, TicketFields(priority="urgent"), by="other", coordinator=True)
        return edited

    monkeypatch.setattr(tickets, "update", another_edit_lands_first)
    changed = await coordinator.edit(low.id, TicketFields(priority="high"), by=COORDINATOR)
    assert changed.undo is not None
    with pytest.raises(ConflictError, match="priority changed since: it is urgent now, not high"):
        await undo.undo(changed.undo, OWNER)
    assert (await tickets.get(low.id)).priority == "urgent"
