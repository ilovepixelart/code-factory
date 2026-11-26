"""Creating, reading, editing and listing tickets, against the test database.

Sequences are not transactional: a rolled-back test still moves numbering on, so a number is
expected relative to one the test was just issued. Expected values come from the previous
implementation's ticket goldens (a minimal ticket's defaults) and its board order (rank first,
unranked last, then the number), worked by hand.
"""

import pytest

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.tickets.models import (
    Column,
    DocumentName,
    DocumentWrite,
    NewTicket,
    Ticket,
    TicketFields,
    TicketFilter,
)
from code_factory.tickets.service import ActivityService, DocumentService, TicketService
from ticket_values import NOW, OWNER


def new(title: str = "A ticket", **fields: object) -> NewTicket:
    return NewTicket.model_validate({"repository": "sample", "title": title, **fields})


async def test_a_new_ticket_gets_the_next_number_and_the_defaults(tickets: TicketService) -> None:
    first = await tickets.create(new("Minimal"), by=OWNER)
    second = await tickets.create(new("Next"), by=OWNER)
    assert second.number == first.number + 1
    assert second.id == f"CF-{second.number}"
    assert first.model_dump(exclude={"id", "number"}) == {
        "repository": "sample",
        "title": "Minimal",
        "type": "feature",
        "description": "",
        "labels": [],
        "priority": "",
        "assignee": "",
        "due": "",
        "blocked": "",
        "rank": 0,
        "e2e": "",
        "tests": "",
        "budget": "",
        "parallel": "",
        "source": "",
        "steps": "",
        "pages": "",
        "parent": "",
        "blocked_by": [],
        "caused_by": [],
        "archived": False,
        "branch": "",
        "pull_request": None,
        "merged": False,
        "column": Column.SPEC,
        "created_at": NOW,
        "updated_at": NOW,
    }


async def test_a_created_ticket_reads_back_by_its_id(tickets: TicketService) -> None:
    created = await tickets.create(
        new("Read me", labels=["ui"], priority="high", due="2026-10-04"), by=OWNER
    )
    assert await tickets.get(created.id) == created


async def test_an_unknown_ticket_is_not_found_by_id(tickets: TicketService) -> None:
    with pytest.raises(NotFoundError, match="CF-999999 does not exist"):
        await tickets.get("CF-999999")


async def test_an_edit_changes_only_the_fields_it_names(tickets: TicketService) -> None:
    created = await tickets.create(new("Before", assignee="alex", labels=["ui"]), by=OWNER)
    edited = await tickets.update(
        created.id, TicketFields(title=" After ", labels=[], assignee="alex"), by=OWNER
    )
    assert edited.changed == ["title", "labels"]
    assert (edited.ticket.title, edited.ticket.labels, edited.ticket.assignee) == (
        "After",
        [],
        "alex",
    )
    assert await tickets.get(created.id) == edited.ticket


async def test_editing_an_unknown_ticket_is_not_found(tickets: TicketService) -> None:
    with pytest.raises(NotFoundError, match="CF-999999 does not exist"):
        await tickets.update("CF-999999", TicketFields(title="x"), by=OWNER)


async def test_links_read_back_as_ids_in_the_order_written(tickets: TicketService) -> None:
    one = await tickets.create(new("One"), by=OWNER)
    two = await tickets.create(new("Two"), by=OWNER)
    three = await tickets.create(new("Three"), by=OWNER)
    child = await tickets.create(
        new("Child", parent=one.id, blocked_by=[three.id, two.id], caused_by=[one.id]), by=OWNER
    )
    assert (child.parent, child.blocked_by, child.caused_by) == (
        one.id,
        [three.id, two.id],
        [one.id],
    )
    cleared = (
        await tickets.update(child.id, TicketFields(parent="", blocked_by=[two.id]), by=OWNER)
    ).ticket
    assert (cleared.parent, cleared.blocked_by, cleared.caused_by) == ("", [two.id], [one.id])


async def test_a_link_to_a_ticket_that_does_not_exist_is_refused(tickets: TicketService) -> None:
    with pytest.raises(BadRequestError, match="CF-999999 does not exist"):
        await tickets.create(new("Orphan", parent="CF-999999"), by=OWNER)


async def test_a_ticket_cannot_link_to_itself(tickets: TicketService) -> None:
    ticket = await tickets.create(new("Self"), by=OWNER)
    with pytest.raises(BadRequestError, match=f"{ticket.id} cannot name itself as blocked_by"):
        await tickets.update(ticket.id, TicketFields(blocked_by=[ticket.id]), by=OWNER)


async def test_a_parent_that_descends_from_the_ticket_is_refused(tickets: TicketService) -> None:
    top = await tickets.create(new("Top"), by=OWNER)
    middle = await tickets.create(new("Middle", parent=top.id), by=OWNER)
    bottom = await tickets.create(new("Bottom", parent=middle.id), by=OWNER)
    with pytest.raises(BadRequestError, match=f"{bottom.id} descends from {top.id}"):
        await tickets.update(top.id, TicketFields(parent=bottom.id), by=OWNER)


async def test_the_board_order_is_rank_first_unranked_last_then_number(
    tickets: TicketService,
) -> None:
    unranked_a = await tickets.create(new("Unranked a", repository="ordered"), by=OWNER)
    ranked_2 = await tickets.create(new("Ranked 2", repository="ordered", rank=2), by=OWNER)
    unranked_b = await tickets.create(new("Unranked b", repository="ordered"), by=OWNER)
    ranked_1 = await tickets.create(new("Ranked 1", repository="ordered", rank=1), by=OWNER)
    listed = await tickets.list(TicketFilter(repository="ordered"))
    assert [t.id for t in listed] == [ranked_1.id, ranked_2.id, unranked_a.id, unranked_b.id]


async def test_a_list_filters_by_label_and_parent(tickets: TicketService) -> None:
    parent = await tickets.create(new("Parent", repository="filtered"), by=OWNER)
    child_ui = await tickets.create(
        new("Child ui", repository="filtered", parent=parent.id, labels=["ui", "agents"]),
        by=OWNER,
    )
    await tickets.create(new("Child plain", repository="filtered", parent=parent.id), by=OWNER)
    await tickets.create(new("Other ui", repository="filtered", labels=["ui"]), by=OWNER)
    listed = await tickets.list(TicketFilter(repository="filtered", parent=parent.id, label="ui"))
    assert [t.id for t in listed] == [child_ui.id]


async def test_the_view_is_the_ticket_its_document_index_and_its_latest_records(
    tickets: TicketService, activity: ActivityService, documents: DocumentService
) -> None:
    ticket = await tickets.create(new("Viewed"), by=OWNER)
    await documents.write_document(
        ticket.id, DocumentName.SPEC, DocumentWrite(content="# Spec"), by=OWNER
    )
    for word in ("one", "two", "three", "four", "five"):
        await activity.record_note(ticket.id, word, "note", by=OWNER)
    view = await tickets.get_view(ticket.id)
    assert view.ticket == await tickets.get(ticket.id)
    assert [(d.name, d.version, d.chars) for d in view.documents] == [(DocumentName.SPEC, 1, 6)]
    assert [r.data.get("text") for r in view.recent_activity] == [
        "five",
        "four",
        "three",
        "two",
        "one",
    ]


async def test_the_repository_of_a_ticket_is_its_own_and_none_when_there_is_no_such_ticket(
    tickets: TicketService, ticket: Ticket
) -> None:
    assert await tickets.repository_of(ticket.id) == "sample"
    assert await tickets.repository_of("CF-999999") is None
    assert await tickets.repository_of("CF-99999999999999999999") is None  # beyond bigint
