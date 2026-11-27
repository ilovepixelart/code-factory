"""Rank, column limits, delete and duplicate."""

import pytest

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.models import Column, TicketFilter
from code_factory.tickets.service import ActivityService, TicketService
from code_factory.undo.service import UndoService
from write_fakes import RunningOn
from write_values import address, exactly, file

OWNER = "owner:owner"
WHOLE = "a limit must be a positive whole number"


async def test_set_rank_writes_the_rank_and_records_it_once(
    writes: TicketWriteService, tickets: TicketService, activity: ActivityService
) -> None:
    one = await file(tickets, "One")

    await writes.set_rank(address(one), 3, OWNER)
    await writes.set_rank(address(one), 3, OWNER)

    assert (await tickets.get(one.id)).rank == 3
    records = (await activity.list_activity(one.id, kinds=["field"])).items
    assert [(r.data, r.by) for r in records] == [({"name": "rank", "value": "3"}, OWNER)]


async def test_a_negative_rank_and_a_missing_ticket_are_refused(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    one = await file(tickets, "One")
    with pytest.raises(BadRequestError, match=exactly("a rank is not negative")):
        await writes.set_rank(address(one), -1, OWNER)
    given = address(one).model_copy(update={"id": "CF-999999"})
    with pytest.raises(NotFoundError, match=exactly("no such ticket")):
        await writes.set_rank(given, 1, OWNER)
    await writes.set_rank(address(one), 0, OWNER)


async def test_a_limit_is_set_replaced_and_cleared_without_touching_the_other_columns(
    writes: TicketWriteService,
) -> None:
    for stage, raw in (("spec", 2), ("build", 3), ("build", 5)):
        answer = await writes.set_column_limit(stage, raw)
        assert (answer.notice, answer.undo) == ("", None)
    assert await writes.column_limits() == {"spec": 2, "build": 5}

    await writes.set_column_limit("spec", None)

    assert await writes.column_limits() == {"build": 5}


async def test_clearing_a_column_that_has_no_limit_is_fine(writes: TicketWriteService) -> None:
    await writes.set_column_limit("review", None)

    assert await writes.column_limits() == {}


@pytest.mark.parametrize("raw", [0, -1, 2.5, "3", "many", "", True])
async def test_a_limit_that_is_not_a_positive_whole_number_is_refused_and_nothing_changes(
    writes: TicketWriteService, raw: object
) -> None:
    await writes.set_column_limit("build", 3)

    with pytest.raises(BadRequestError) as refused:
        await writes.set_column_limit("build", raw)

    assert str(refused.value) == WHOLE
    assert await writes.column_limits() == {"build": 3}


async def test_a_name_that_is_no_column_is_refused_before_its_value_is_read(
    writes: TicketWriteService,
) -> None:
    for raw in (2, "many"):
        with pytest.raises(BadRequestError, match=exactly("unknown stage later")):
            await writes.set_column_limit("later", raw)
    assert await writes.column_limits() == {}


async def test_a_delete_hides_the_ticket_and_offers_an_undo_that_brings_back_its_number(
    writes: TicketWriteService, tickets: TicketService, undo: UndoService
) -> None:
    one = await file(tickets, "One")

    answer = await writes.delete(address(one))

    assert answer.notice == f"Deleted {one.id}"
    assert await tickets.list(TicketFilter(archived=None)) == []
    with pytest.raises(NotFoundError):
        await tickets.get(one.id)
    assert answer.undo is not None
    await undo.undo(answer.undo, OWNER)
    assert (await tickets.get(one.id)).title == "One"


async def test_a_deleted_ticket_s_number_is_never_given_again(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    one = await file(tickets, "One")
    await writes.delete(address(one))

    made = await writes.create("sample", {"title": "Next"}, OWNER)

    assert (await tickets.get(made.id)).number == one.number + 1


async def test_a_ticket_an_agent_runs_on_is_not_deleted(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    busy = await file(tickets, "Busy")
    idle = await file(tickets, "Idle")
    check = RunningOn(busy.id)
    writes.bind_active_runs(check)

    with pytest.raises(ConflictError) as refused:
        await writes.delete(address(busy))
    await writes.delete(address(idle))

    assert str(refused.value) == "an agent is running on this ticket; stop it first"
    assert (await tickets.get(busy.id)).title == "Busy"
    assert [a.id for a in check.asked] == [busy.id, idle.id]


async def test_with_no_run_check_bound_a_delete_is_allowed(
    writes: TicketWriteService, tickets: TicketService
) -> None:
    one = await file(tickets, "One")

    await writes.delete(address(one))

    assert await tickets.list(TicketFilter(archived=None)) == []


async def test_deleting_a_missing_ticket_is_not_found(writes: TicketWriteService) -> None:
    from code_factory.tickets.models import TicketAddress  # noqa: PLC0415

    with pytest.raises(NotFoundError, match=exactly("no such ticket")):
        await writes.delete(TicketAddress(repository="sample", id="CF-999999"))


async def test_a_duplicate_copies_the_card_and_leaves_state_and_links_behind(
    writes: TicketWriteService, tickets: TicketService, activity: ActivityService
) -> None:
    blocker = await file(tickets, "Blocker")
    original = await file(
        tickets, "New thing", type="bug", description="Why.", labels=["a", "b"], priority="high",
        assignee="ann", due="2026-11-01", e2e="e", tests="t", budget="5", parallel="2",
        source="https://x/1", pages="p", blocked_by=[blocker.id], parent=blocker.id,
    )  # fmt: skip
    await tickets.set_branch(original.id, "feat/x", by=OWNER)
    await tickets.archive(original.id, by=OWNER)

    copy = await writes.duplicate(address(original), OWNER)

    made = await tickets.get(copy.id)
    assert (made.title, made.type, made.description, made.labels, made.priority) == (
        "New thing (copy)", "bug", "Why.", ["a", "b"], "high",
    )  # fmt: skip
    assert (made.assignee, made.due, made.e2e, made.tests) == ("ann", "2026-11-01", "e", "t")
    assert (made.branch, made.column, made.archived, made.rank) == ("", Column.SPEC, False, 0)
    assert (made.blocked_by, made.parent, made.budget, made.parallel) == ([], "", "", "")
    assert (made.source, made.pages, made.steps) == ("", "", "")
    records = (await activity.list_activity(copy.id)).items
    assert [(r.kind, r.data) for r in records] == [
        ("created", {"type": "bug", "from": original.id})
    ]


async def test_duplicating_a_missing_ticket_is_not_found(writes: TicketWriteService) -> None:
    from code_factory.tickets.models import TicketAddress  # noqa: PLC0415

    with pytest.raises(NotFoundError, match=exactly("no such ticket")):
        await writes.duplicate(TicketAddress(repository="sample", id="CF-999999"), OWNER)
