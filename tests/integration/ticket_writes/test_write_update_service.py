"""Editing a ticket: fields, refusals, the column and archiving (G[7] to G[27], G[68])."""

import pytest

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.stages.service import StageService
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.models import Column, TicketAddress
from code_factory.tickets.service import ActivityService, TicketService
from write_fakes import FakeGit
from write_values import address, exactly, file

OWNER = "owner:owner"


async def fields_recorded(activity: ActivityService, ticket: str) -> list[tuple[str, object]]:
    items = (await activity.list_activity(ticket, kinds=["field"])).items
    return [(str(r.data["name"]), r.data["value"]) for r in items]


async def test_an_edit_writes_the_fields_and_records_each_changed_one_in_order(
    writes: TicketWriteService, tickets: TicketService, activity: ActivityService
) -> None:
    one = await file(tickets, "Two", priority="low")

    answer = await writes.update(
        address(one),
        {"title": " Renamed ", "priority": "low", "labels": "x, y", "description": "A story.\n"},
        OWNER,
    )

    ticket = await tickets.get(one.id)
    assert (ticket.title, ticket.labels, ticket.description) == ("Renamed", ["x", "y"], "A story.")
    assert answer.changed == ["title", "labels", "description"]
    assert (answer.notice, answer.undo) == ("", None)
    assert await fields_recorded(activity, one.id) == [
        ("title", "Renamed"), ("labels", "x, y"), ("description", ""),
    ]  # fmt: skip
    first = (await activity.list_activity(one.id, kinds=["field"])).items[0]
    assert first.by == OWNER


async def test_an_edit_that_changes_nothing_records_nothing(
    writes: TicketWriteService, tickets: TicketService, activity: ActivityService
) -> None:
    one = await file(tickets, "Same", labels=["a", "b"])

    answer = await writes.update(address(one), {"title": "Same", "labels": "a,b"}, OWNER)

    assert answer.changed == []
    assert await fields_recorded(activity, one.id) == []


@pytest.mark.parametrize(
    ("fields", "sentence"),
    [
        ({"budget": "abc"}, "budget must be a number of dollars"),
        ({"budget": "-1"}, "budget must be a number of dollars"),
        ({"budget": "1__0"}, "budget must be a number of dollars"),
        ({"blocked_by": "CF-999999"}, "no ticket CF-999999"),
        ({"priority": "soon"}, "unknown priority soon"),
        ({"archived": "maybe"}, "bad archived maybe"),
        ({"title": "   "}, "a ticket needs a title"),
        ({"title": "a\nb"}, "title holds a line break"),
        ({"type": "epic"}, "unknown type epic"),
        ({"nope": "x"}, "unknown fields ['nope']"),
        ({"rank": "3"}, "unknown fields ['rank']"),
    ],
)
async def test_a_refused_edit_leaves_the_ticket_as_it_was(
    writes: TicketWriteService,
    tickets: TicketService,
    activity: ActivityService,
    fields: dict[str, str],
    sentence: str,
) -> None:
    one = await file(tickets, "Keep")
    before = await tickets.get(one.id)

    with pytest.raises(BadRequestError) as refused:
        await writes.update(address(one), {"description": "changed first", **fields}, OWNER)

    assert str(refused.value) == sentence
    assert await tickets.get(one.id) == before
    assert await fields_recorded(activity, one.id) == []


@pytest.mark.parametrize(
    ("budget", "stored"),
    [("0", "0"), ("1000", "1000"), (" 3.5 ", "3.5"), ("1e3", "1000")],
)
async def test_a_budget_is_stored_as_the_amount_it_names(
    writes: TicketWriteService, tickets: TicketService, budget: str, stored: str
) -> None:
    one = await file(tickets, "Budget")

    await writes.update(address(one), {"budget": budget}, OWNER)

    assert (await tickets.get(one.id)).budget == stored


async def test_a_ticket_cannot_block_itself_or_name_one_that_is_not_there(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    one = await file(tickets, "One")

    with pytest.raises(BadRequestError, match=exactly(f"{one.id} cannot link to itself")):
        await writes.update(address(one), {"blocked_by": one.id}, OWNER)
    with pytest.raises(BadRequestError, match=exactly("no ticket CF-999999")):
        await writes.update(address(one), {"blocked_by": "CF-999999"}, OWNER)


async def test_a_parent_that_would_make_a_loop_is_refused_and_a_list_is_normalised(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    top = await file(tickets, "Top")
    low = await file(tickets, "Low", parent=top.id)
    other = await file(tickets, "Other")

    with pytest.raises(BadRequestError, match=exactly(f"parent {low.id} would make a loop")):
        await writes.update(address(top), {"parent": low.id}, OWNER)
    await writes.update(address(other), {"blocked_by": f" {top.id} ,, {low.id}"}, OWNER)

    assert (await tickets.get(other.id)).blocked_by == [top.id, low.id]


async def test_an_old_link_to_a_deleted_ticket_does_not_freeze_the_card(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    gone = await file(tickets, "Gone")
    held = await file(tickets, "Held", blocked_by=[gone.id])
    await writes.delete(address(gone))

    await writes.update(address(held), {"title": "Still editable", "blocked_by": gone.id}, OWNER)

    assert (await tickets.get(held.id)).title == "Still editable"


async def test_an_edit_of_a_missing_ticket_or_one_of_another_repository_is_not_found(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    one = await file(tickets, "One")

    for ref in (
        TicketAddress(repository="sample", id="CF-999999"),
        TicketAddress(repository="second", id=one.id),
        TicketAddress(repository="nowhere", id=one.id),
        TicketAddress(repository="sample", id="nonsense"),
    ):
        with pytest.raises(NotFoundError, match=exactly("no such ticket")):
            await writes.update(ref, {"title": "Nobody"}, OWNER)


async def test_a_column_the_stages_module_refuses_is_refused_with_its_sentence(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    one = await file(tickets, "Plain")

    with pytest.raises(BadRequestError) as refused:
        await writes.update(address(one), {"stage": "review", "title": "Never"}, OWNER)

    assert str(refused.value) == f"{one.id} moves one column at a time: Build is next"
    assert (await tickets.get(one.id)).title == "Plain"


async def test_a_column_is_declared_exactly_with_the_fields_of_the_same_edit(
    writes: TicketWriteService, tickets: TicketService, stages: StageService
) -> None:
    one = await file(tickets, "Plain")

    answer = await writes.update(address(one), {"stage": "spec", "labels": "x, y"}, OWNER)

    assert (await stages.assess(one.id)).declared == "spec"
    assert (await tickets.get(one.id)).labels == ["x", "y"]
    assert answer.changed == ["labels", "stage"]


async def test_archiving_answers_a_notice_and_an_undo_and_restoring_the_same(
    writes: TicketWriteService, tickets: TicketService, activity: ActivityService
) -> None:
    one = await file(tickets, "Two")

    archived = await writes.update(address(one), {"archived": "true"}, OWNER)
    again = await writes.update(address(one), {"archived": "on"}, OWNER)
    restored = await writes.update(address(one), {"archived": ""}, OWNER)

    assert (archived.notice, archived.changed) == (f"Archived {one.id}", ["archived"])
    assert archived.undo is not None
    assert (again.notice, again.undo, again.changed) == ("", None, [])
    assert (restored.notice, restored.changed) == (f"Restored {one.id}", ["archived"])
    kinds = [r.kind for r in (await activity.list_activity(one.id)).items]
    assert kinds == ["created", "archived", "restored"]


async def test_a_branch_is_checked_against_git_only_when_it_changes(
    writes: TicketWriteService, tickets: TicketService, git: FakeGit
) -> None:
    git.local = frozenset({"feat/one"})
    one = await file(tickets, "One")

    await writes.update(address(one), {"branch": "feat/one"}, OWNER)
    assert (await tickets.get(one.id)).column is Column.BUILD
    calls = len(git.calls)
    git.local = frozenset()
    await writes.update(address(one), {"branch": "feat/one", "title": "Again"}, OWNER)
    with pytest.raises(BadRequestError, match="no branch feat/two exists"):
        await writes.update(address(one), {"branch": "feat/two"}, OWNER)
    await writes.update(address(one), {"branch": ""}, OWNER)

    assert len(git.calls) == calls + 1
    assert (await tickets.get(one.id)).column is Column.SPEC
