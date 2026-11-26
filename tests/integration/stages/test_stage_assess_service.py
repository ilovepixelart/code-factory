"""Where a ticket stands, from its stored facts, its pull request and its release. Cards are the
previous delivery golden's, built through the real ticket, release and observer paths."""

from collections.abc import Awaitable

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection

from code_factory.platform.errors import NotFoundError
from code_factory.releases.service import ReleaseService
from code_factory.stages.service import StageService
from code_factory.tickets.models import NewTicket, PullRequest, PullRequestState, Ticket
from code_factory.tickets.service import TicketService
from stage_fakes import FakeClock, FakeFacts
from stage_values import details, shape
from ticket_values import OWNER

URL = "https://github.com/o/r/pull/1"
REPOSITORY = "sample"


async def new_ticket(tickets: TicketService, title: str = "Another", branch: str = "") -> Ticket:
    made = await tickets.create(NewTicket(repository=REPOSITORY, title=title), by=OWNER)
    return await tickets.set_branch(made.id, branch, by=OWNER) if branch else made


async def test_a_pushed_branch_with_a_commit_and_a_recorded_pull_request_is_in_review(
    stages: StageService, tickets: TicketService, started: Ticket, facts: FakeFacts
) -> None:
    await tickets.set_pull_request(
        started.id, PullRequest(number=1, state=PullRequestState.OPEN, url=URL), by=OWNER
    )
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe()

    found = await stages.assess(started.id)

    assert (found.derived, found.stage, found.work_done, found.landed) == (
        "review",
        "review",
        True,
        False,
    )
    assert shape(found.checklist) == "PrPrPr-r-o"
    assert details(found.checklist)[:3] == ["a branch", f"a commit on {started.branch}", URL]
    assert found.refusals["merged"] == f"{started.id} needs {URL} before Merged"
    assert found.hold == {
        "stage": "merged",
        "detail": "a merge into main",
        "summary": "a merge into main",
    }


async def test_a_pushed_branch_without_a_pull_request_stays_in_build_and_says_so(
    stages: StageService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True, pushed=True)
    await stages.observe()

    found = await stages.assess(started.id)

    assert (found.stage, found.work_done) == ("build", False)
    assert details(found.checklist)[2] == f"a pull request for {started.branch}"
    assert (
        found.refusals["review"] == f"{started.id} needs a commit on {started.branch} before Review"
    )
    assert found.refusals["merged"] == f"{started.id} moves one column at a time: Review is next"
    assert found.hold == {
        "stage": "build",
        "detail": f"a commit on {started.branch}",
        "summary": f"a commit on {started.branch}",
    }


async def test_a_ticket_with_no_branch_is_at_spec_and_told_how_to_start(
    stages: StageService, tickets: TicketService
) -> None:
    bare = await new_ticket(tickets)

    found = await stages.assess(bare.id)

    assert (found.stage, found.hold) == (
        "spec",
        {"stage": "spec", "detail": "a branch", "summary": "a branch"},
    )
    assert found.refusals["build"] == (
        f"{bare.id} needs a branch before Build: "
        f"start an agent on it, or run code-factory start {bare.id}"
    )


async def test_a_ticket_not_yet_observed_counts_its_declared_branch_as_started_and_is_not_trusted(
    stages: StageService, started: Ticket
) -> None:
    found = await stages.assess(started.id)

    assert (found.stage, found.facts_known, found.observed_at) == ("build", False, None)


async def test_an_observed_ticket_is_trusted_and_says_when_it_was_observed(
    stages: StageService, started: Ticket, facts: FakeFacts, clock: FakeClock
) -> None:
    facts.give(started.id, local=True)
    await stages.observe()

    found = await stages.assess(started.id)

    assert found.facts_known
    assert found.observed_at == clock.now


async def test_facts_read_for_another_branch_are_not_used(
    stages: StageService, tickets: TicketService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe()
    await tickets.set_branch(started.id, "feat/other", by=OWNER)

    found = await stages.assess(started.id)

    assert not found.facts_known
    assert details(found.checklist)[1] == "a commit on feat/other"
    assert found.checklist[1].present is False


async def test_a_merge_the_ticket_records_puts_it_in_merged_whatever_git_says(
    stages: StageService, tickets: TicketService, started: Ticket
) -> None:
    await tickets.set_merged(started.id, True, by=OWNER)

    found = await stages.assess(started.id)

    assert (found.stage, found.landed) == ("merged", True)
    assert shape(found.checklist) == "PrPrPrPr-o"


async def test_a_closed_pull_request_does_not_put_a_ticket_in_review(
    stages: StageService, tickets: TicketService, started: Ticket, facts: FakeFacts
) -> None:
    await tickets.set_pull_request(
        started.id, PullRequest(number=1, state=PullRequestState.CLOSED, url=URL), by=OWNER
    )
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe()

    assert (await stages.assess(started.id)).stage == "build"


async def test_a_release_naming_the_ticket_takes_it_off_the_board_as_released(
    stages: StageService,
    tickets: TicketService,
    releases: ReleaseService,
    started: Ticket,
) -> None:
    await tickets.set_merged(started.id, True, by=OWNER)
    await releases.draft(REPOSITORY, "0.1.0", by=OWNER)
    await releases.publish(REPOSITORY, "0.1.0", by=OWNER)

    found = await stages.assess(started.id)

    assert (found.stage, found.landed) == ("released", True)
    assert details(found.checklist)[4] == "0.1.0"
    assert shape(found.checklist) == "PrPrPrPrPo"


async def test_a_released_ticket_with_no_branch_holds_nothing(
    stages: StageService, tickets: TicketService, releases: ReleaseService
) -> None:
    bare = await new_ticket(tickets)
    await tickets.set_merged(bare.id, True, by=OWNER)
    await releases.draft(REPOSITORY, "0.1.0", by=OWNER)
    await releases.publish(REPOSITORY, "0.1.0", by=OWNER)

    found = await stages.assess(bare.id)

    assert (found.stage, found.landed, found.hold) == ("released", True, None)


async def test_a_ticket_that_does_not_exist_is_not_found(stages: StageService) -> None:
    with pytest.raises(NotFoundError, match="CF-99999 does not exist"):
        await stages.assess("CF-99999")


async def test_assessing_many_gives_the_same_answers_as_one_at_a_time(
    stages: StageService, tickets: TicketService, started: Ticket, facts: FakeFacts
) -> None:
    other = await new_ticket(tickets, "Other", "feat/CF-2")
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe()

    many = await stages.assess_many([started.id, other.id])

    assert set(many) == {started.id, other.id}
    assert many[started.id] == await stages.assess(started.id)
    assert many[other.id] == await stages.assess(other.id)


async def test_assessing_many_without_ids_answers_every_live_ticket(
    stages: StageService, tickets: TicketService, started: Ticket
) -> None:
    other = await new_ticket(tickets, "Other")
    archived = await new_ticket(tickets, "Gone")
    await tickets.archive(archived.id, by=OWNER)

    assert set(await stages.assess_many()) == {started.id, other.id, archived.id}
    assert await stages.assess_many([]) == {}


async def counted(connection: AsyncConnection, work: Awaitable[object]) -> int:
    seen: list[str] = []

    def record(_c: object, _cur: object, statement: str, *_rest: object) -> None:
        seen.append(statement)

    event.listen(connection.sync_engine, "before_cursor_execute", record)
    try:
        await work
    finally:
        event.remove(connection.sync_engine, "before_cursor_execute", record)
    return len([statement for statement in seen if statement.lstrip().upper().startswith("SELECT")])


async def test_assessing_many_asks_the_database_the_same_number_of_questions_for_any_number(
    stages: StageService, tickets: TicketService, connection: AsyncConnection
) -> None:
    few = [(await new_ticket(tickets, f"T{n}", f"feat/few-{n}")).id for n in range(3)]
    small = await counted(connection, stages.assess_many(few))
    many = [(await new_ticket(tickets, f"M{n}", f"feat/many-{n}")).id for n in range(30)]

    large = await counted(connection, stages.assess_many([*few, *many]))

    assert small == large
    assert large <= 6


async def test_a_ticket_is_reviewable_once_its_work_is_done_and_before_it_is_in_review(
    stages: StageService, tickets: TicketService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True)
    await stages.observe()
    assert not await stages.is_reviewable(started.id)

    facts.give(started.id, local=True, has_commits=True)
    await stages.observe()
    assert await stages.is_reviewable(started.id)

    await tickets.set_pull_request(
        started.id, PullRequest(number=1, state=PullRequestState.OPEN, url=URL), by=OWNER
    )
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe()
    assert not await stages.is_reviewable(started.id)


async def test_a_merge_the_ticket_records_counts_although_git_says_not_merged(
    stages: StageService, tickets: TicketService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True, pushed=True, has_commits=True, merged=False)
    await stages.observe()
    await tickets.set_merged(started.id, True, by=OWNER)

    found = await stages.assess(started.id)

    assert (found.derived, found.landed) == ("merged", True)


async def test_a_merge_recorded_on_the_pull_request_counts_although_git_says_not_merged(
    stages: StageService, tickets: TicketService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True, pushed=True, has_commits=True, merged=False)
    await stages.observe()
    await tickets.set_pull_request(
        started.id, PullRequest(number=1, state=PullRequestState.MERGED, url=URL), by=OWNER
    )

    assert (await stages.assess(started.id)).derived == "merged"


async def test_a_ticket_neither_git_nor_the_ticket_calls_merged_is_not_merged(
    stages: StageService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True, pushed=True, has_commits=True, merged=False)
    await stages.observe()

    assert (await stages.assess(started.id)).landed is False
