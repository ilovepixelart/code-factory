"""The unit of work other modules write tickets through (the ticket-writes contract).

A unit is one transaction: it holds a lock per repository it names, reads and writes tickets and
records, and keeps nothing when its block raises. A trashed ticket is hidden from every read.
Expected values are worked by hand from ticket-writes section 6.
"""

import uuid

import pytest

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.tickets.models import (
    LinkGraph,
    NewTicket,
    TicketAddress,
    TicketFields,
    TicketFilter,
)
from code_factory.tickets.service import ActivityService, TicketService
from ticket_values import OWNER

# Advisory locks belong to the whole database, so a name shared with another worker or run would
# make this test wait for it: every process names its repositories afresh.
SUFFIX = uuid.uuid4().hex[:8]
REPO = f"unit-repo-{SUFFIX}"
DROPPED = f"dropped-{SUFFIX}"
WAIT = 1.0


async def make(tickets: TicketService, title: str, repository: str = REPO) -> TicketAddress:
    made = await tickets.create(NewTicket(repository=repository, title=title), by=OWNER)
    return TicketAddress(repository=repository, id=made.id)


async def test_a_unit_reads_a_live_ticket_of_its_repository_only(tickets: TicketService) -> None:
    one = await make(tickets, "One")
    async with tickets.unit([REPO], wait=WAIT) as unit:
        found = await unit.get(one)
        assert found is not None
        assert (found.id, found.title, found.rank, found.trashed) == (one.id, "One", 0, False)
        assert await unit.get(TicketAddress(repository="elsewhere", id=one.id)) is None
        assert await unit.get(TicketAddress(repository=REPO, id="CF-999999")) is None


async def test_a_trashed_ticket_is_hidden_from_every_read_until_restored(
    tickets: TicketService, activity: ActivityService
) -> None:
    keep = await make(tickets, "Keep")
    gone = await make(tickets, "Gone")
    async with tickets.unit([REPO], wait=WAIT) as unit:
        assert await unit.trash(gone) is True
        assert await unit.trash(gone) is False
        assert await unit.get(gone) is None
        deleted = await unit.get_deleted(gone)
        assert deleted is not None
        assert (deleted.id, deleted.trashed) == (gone.id, True)
        assert await unit.get_deleted(keep) is None
    assert [t.id for t in await tickets.list(TicketFilter(archived=None))] == [keep.id]
    assert await tickets.open_titles(REPO) == [(keep.id, "Keep")]
    assert [f.id for f in await tickets.flow_facts(REPO)] == [keep.id]
    assert await tickets.count_authored(OWNER, "created") == 1
    with pytest.raises(NotFoundError, match=gone.id):
        await tickets.get(gone.id)
    with pytest.raises(NotFoundError, match=gone.id):
        await activity.list_activity(gone.id)
    async with tickets.unit([REPO], wait=WAIT) as unit:
        assert await unit.restore(gone) is True
        assert await unit.restore(gone) is False
        assert await unit.get_deleted(gone) is None
    assert (await tickets.get(gone.id)).title == "Gone"


async def test_a_ticket_cannot_be_linked_to_a_trashed_one(tickets: TicketService) -> None:
    gone = await make(tickets, "Gone")
    other = await make(tickets, "Other")
    async with tickets.unit([REPO], wait=WAIT) as unit:
        await unit.trash(gone)
    with pytest.raises(BadRequestError, match=f"{gone.id} does not exist"):
        await tickets.update(other.id, TicketFields(parent=gone.id), by=OWNER)


async def test_insert_allocates_a_number_and_writes_no_record(
    tickets: TicketService, activity: ActivityService
) -> None:
    parent = await make(tickets, "Parent")
    async with tickets.unit([REPO], wait=WAIT) as unit:
        child = await unit.insert(NewTicket(repository=REPO, title="Child", parent=parent.id))
    assert (child.repository, child.id == parent.id) == (REPO, False)
    assert (await tickets.get(child.id)).parent == parent.id
    assert (await activity.list_activity(child.id)).items == []


async def test_save_fields_answers_the_names_it_changed_and_records_nothing(
    tickets: TicketService, activity: ActivityService
) -> None:
    one = await make(tickets, "One")
    async with tickets.unit([REPO], wait=WAIT) as unit:
        changed = await unit.save_fields(one, TicketFields(title="Uno", priority="high"))
        assert changed == ["title", "priority"]
        assert await unit.save_fields(one, TicketFields(title="Uno")) == []
    saved = await tickets.get(one.id)
    assert (saved.title, saved.priority) == ("Uno", "high")
    assert [r.kind for r in (await activity.list_activity(one.id)).items] == ["created"]


async def test_save_fields_of_a_missing_ticket_is_not_found(tickets: TicketService) -> None:
    async with tickets.unit([REPO], wait=WAIT) as unit:
        with pytest.raises(NotFoundError, match="CF-999999"):
            await unit.save_fields(
                TicketAddress(repository=REPO, id="CF-999999"), TicketFields(title="x")
            )


async def test_record_appends_a_record_but_not_one_only_the_review_writes(
    tickets: TicketService, activity: ActivityService
) -> None:
    one = await make(tickets, "One")
    async with tickets.unit([REPO], wait=WAIT) as unit:
        await unit.record(one, "field", {"name": "title", "value": "Uno"}, by=OWNER)
        with pytest.raises(BadRequestError, match="finding is written by the review"):
            await unit.record(one, "finding", {}, by=OWNER)
    records = (await activity.list_activity(one.id, kinds=["field"])).items
    assert [(r.by, r.data) for r in records] == [(OWNER, {"name": "title", "value": "Uno"})]


async def test_set_ranks_skips_an_unknown_id_a_huge_number_and_another_repositorys_ticket(
    tickets: TicketService,
) -> None:
    first = await make(tickets, "First")
    second = await make(tickets, "Second")
    foreign = await make(tickets, "Foreign", "elsewhere")
    async with tickets.unit([REPO], wait=WAIT) as unit:
        await unit.set_ranks(
            REPO,
            {
                first.id: 2,
                second.id: 1,
                foreign.id: 5,
                "CF-999999": 3,
                "CF-99999999999999999999": 4,
            },
        )
    assert [(t.id, t.rank) for t in await tickets.list(TicketFilter(repository=REPO))] == [
        (second.id, 1),
        (first.id, 2),
    ]
    assert (await tickets.get(foreign.id)).rank == 0


async def test_the_link_graph_holds_the_live_tickets_and_their_parents(
    tickets: TicketService,
) -> None:
    parent = await make(tickets, "Parent")
    child = await make(tickets, "Child")
    gone = await make(tickets, "Gone")
    await make(tickets, "Foreign", "elsewhere")
    await tickets.update(child.id, TicketFields(parent=parent.id), by=OWNER)
    async with tickets.unit([REPO], wait=WAIT) as unit:
        await unit.trash(gone)
        graph = await unit.link_graph(REPO)
    assert graph == LinkGraph(ids=[parent.id, child.id], parent_of={child.id: parent.id})


async def test_a_unit_that_raises_keeps_nothing(tickets: TicketService) -> None:
    one = await make(tickets, "One")

    async def stopped() -> None:
        async with tickets.unit([REPO], wait=WAIT) as unit:
            await unit.insert(NewTicket(repository=REPO, title="Never"))
            await unit.trash(one)
            raise RuntimeError("stop")

    with pytest.raises(RuntimeError, match="stop"):
        await stopped()
    assert [t.title for t in await tickets.list(TicketFilter(repository=REPO))] == ["One"]


async def test_a_ticket_core_and_the_repositories_are_read_outside_a_unit(
    tickets: TicketService,
) -> None:
    one = await make(tickets, "One")
    gone = await make(tickets, "Gone", DROPPED)
    await make(tickets, "Other", "another")
    async with tickets.unit([DROPPED], wait=WAIT) as unit:
        await unit.trash(gone)
    core = await tickets.get_core(one)
    assert core is not None
    assert (core.id, core.trashed) == (one.id, False)
    assert await tickets.get_core(gone) is None
    assert await tickets.get_core(TicketAddress(repository="wrong", id=one.id)) is None
    assert {"another", REPO} <= set(await tickets.list_repositories())
    assert DROPPED not in await tickets.list_repositories()
