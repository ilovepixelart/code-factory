"""The facts a ticket's column is read from, and archiving, through the ticket service.

The walk is the previous implementation's rule worked by hand: Spec until a branch, Build while
it has one, Review while its pull request is open, Merged once merged; each move is a `stage`
record with `from` and `to`, archiving an `archived` record and restoring a `restored` one.
"""

import pytest

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.tickets.models import (
    Column,
    PullRequest,
    PullRequestState,
    Ticket,
    TicketFilter,
)
from code_factory.tickets.service import ActivityService, TicketService
from ticket_values import OWNER

OPEN = PullRequest(number=12, state=PullRequestState.OPEN, url="https://example.test/pull/12")


async def moves(activity: ActivityService, ticket: Ticket) -> list[tuple[str, str]]:
    page = await activity.list_activity(ticket.id, kinds=["stage"])
    return [(r.data["from"], r.data["to"]) for r in page.items]


async def test_a_ticket_walks_the_columns_as_its_facts_arrive(
    tickets: TicketService, activity: ActivityService, ticket: Ticket
) -> None:
    built = await tickets.set_branch(ticket.id, "ticket/cf-1", by="run-1")
    assert (built.branch, built.column) == ("ticket/cf-1", Column.BUILD)
    reviewed = await tickets.set_pull_request(ticket.id, OPEN, by="board")
    assert (reviewed.pull_request, reviewed.column) == (OPEN, Column.REVIEW)
    merged_pull = OPEN.model_copy(update={"state": PullRequestState.MERGED})
    merged = await tickets.set_pull_request(ticket.id, merged_pull, by="board")
    assert merged.column is Column.MERGED
    assert await moves(activity, ticket) == [
        ("spec", "build"),
        ("build", "review"),
        ("review", "merged"),
    ]


async def test_taking_facts_away_moves_the_ticket_back(
    tickets: TicketService, activity: ActivityService, ticket: Ticket
) -> None:
    await tickets.set_branch(ticket.id, "ticket/cf-1", by=OWNER)
    await tickets.set_pull_request(ticket.id, OPEN, by=OWNER)
    closed = OPEN.model_copy(update={"state": PullRequestState.CLOSED})
    assert (await tickets.set_pull_request(ticket.id, closed, by=OWNER)).column is Column.BUILD
    gone = await tickets.clear_pull_request(ticket.id, by=OWNER)
    assert (gone.pull_request, gone.column) == (None, Column.BUILD)
    bare = await tickets.clear_branch(ticket.id, by=OWNER)
    assert (bare.branch, bare.column) == ("", Column.SPEC)
    assert await moves(activity, ticket) == [
        ("spec", "build"),
        ("build", "review"),
        ("review", "build"),
        ("build", "spec"),
    ]


async def test_work_merged_by_hand_is_merged_without_a_branch(
    tickets: TicketService, ticket: Ticket
) -> None:
    assert (await tickets.set_merged(ticket.id, True, by=OWNER)).column is Column.MERGED
    assert (await tickets.set_merged(ticket.id, False, by=OWNER)).column is Column.SPEC


async def test_a_fact_that_changes_nothing_records_nothing(
    tickets: TicketService, activity: ActivityService, ticket: Ticket
) -> None:
    await tickets.set_branch(ticket.id, "ticket/cf-1", by=OWNER)
    await tickets.set_branch(ticket.id, "ticket/cf-1", by=OWNER)
    await tickets.archive(ticket.id, by=OWNER)
    await tickets.archive(ticket.id, by=OWNER)
    page = await activity.list_activity(ticket.id)
    assert [r.kind for r in page.items] == ["created", "stage", "archived"]


async def test_a_branch_git_would_misread_is_refused(
    tickets: TicketService, ticket: Ticket
) -> None:
    with pytest.raises(BadRequestError, match=r"bad branch a\.\.b: it holds \.\."):
        await tickets.set_branch(ticket.id, "a..b", by=OWNER)
    assert (await tickets.get(ticket.id)).branch == ""


async def test_an_archived_ticket_leaves_the_board_and_comes_back(
    tickets: TicketService, activity: ActivityService, ticket: Ticket
) -> None:
    archived = await tickets.archive(ticket.id, by=OWNER)
    assert archived.archived
    on_board = await tickets.list(TicketFilter(repository="sample"))
    assert ticket.id not in [t.id for t in on_board]
    in_archive = await tickets.list(TicketFilter(repository="sample", archived=True))
    assert ticket.id in [t.id for t in in_archive]
    restored = await tickets.unarchive(ticket.id, by=OWNER)
    assert not restored.archived
    assert ticket.id in [t.id for t in await tickets.list(TicketFilter(repository="sample"))]
    kinds = [r.kind for r in (await activity.list_activity(ticket.id)).items]
    assert kinds == ["created", "archived", "restored"]


async def test_a_list_by_column_answers_only_that_column(
    tickets: TicketService, ticket: Ticket
) -> None:
    await tickets.set_branch(ticket.id, "ticket/cf-1", by=OWNER)
    building = await tickets.list(TicketFilter(repository="sample", column=Column.BUILD))
    assert ticket.id in [t.id for t in building]
    specs = await tickets.list(TicketFilter(repository="sample", column=Column.SPEC))
    assert ticket.id not in [t.id for t in specs]


async def test_a_fact_on_an_unknown_ticket_is_not_found(tickets: TicketService) -> None:
    with pytest.raises(NotFoundError, match="CF-999999 does not exist"):
        await tickets.archive("CF-999999", by=OWNER)
