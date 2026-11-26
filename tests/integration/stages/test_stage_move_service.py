"""Moving a ticket by hand: one earned column at a time, the pin it leaves and the record of it.
The sentences are the previous implementation's move steps golden, ids rewritten to CF."""

from typing import Any

import pytest

from code_factory.platform.errors import BadRequestError, NotFoundError, UnavailableError
from code_factory.stages.models import MoveRefusedError
from code_factory.stages.service import StageService
from code_factory.tickets.models import NewTicket, PullRequest, PullRequestState, Ticket
from code_factory.tickets.service import ActivityService, TicketService
from stage_fakes import FakeFacts
from ticket_values import OWNER

REPOSITORY = "sample"


async def plain(tickets: TicketService, title: str = "Plain") -> Ticket:
    return await tickets.create(NewTicket(repository=REPOSITORY, title=title), by=OWNER)


async def last_stage_record(activity: ActivityService, ticket: str) -> dict[str, object]:
    page = await activity.list_activity(ticket, kinds=["stage"], newest_first=True, limit=1)
    return dict(page.items[0].data)


async def test_a_move_back_declares_the_column_and_records_where_it_came_from(
    stages: StageService, activity: ActivityService, started: Ticket
) -> None:
    moved = await stages.move(started.id, "spec", OWNER)

    assert (moved.from_stage, moved.to_stage) == ("build", "spec")
    assert (moved.declared_before, moved.declared_after, moved.changed) == ("", "spec", True)
    found = await stages.assess(started.id)
    assert (found.declared, found.derived, found.stage) == ("spec", "build", "spec")
    assert await last_stage_record(activity, started.id) == {"from": "build", "to": "spec"}


async def test_a_drop_on_the_column_the_evidence_reached_declares_nothing_and_records_nothing(
    stages: StageService, activity: ActivityService, started: Ticket
) -> None:
    before = (await activity.list_activity(started.id, kinds=["stage"])).items

    moved = await stages.move(started.id, "build", OWNER)

    assert (moved.declared_after, moved.changed) == ("", False)
    assert (await stages.assess(started.id)).declared == ""
    assert (await activity.list_activity(started.id, kinds=["stage"])).items == before


async def test_a_declared_column_is_replaced_by_the_next_move(
    stages: StageService, started: Ticket
) -> None:
    await stages.move(started.id, "spec", OWNER)

    moved = await stages.move(started.id, "build", OWNER)

    assert (moved.declared_before, moved.declared_after, moved.changed) == ("spec", "build", True)
    assert (await stages.assess(started.id)).declared == "build"


async def test_a_move_to_the_column_already_declared_changes_nothing(
    stages: StageService, started: Ticket
) -> None:
    await stages.move(started.id, "spec", OWNER)

    again = await stages.move(started.id, "spec", OWNER)

    assert (again.declared_before, again.declared_after, again.changed) == ("spec", "spec", False)


async def test_a_move_the_evidence_does_not_earn_is_refused_with_the_sentence_and_writes_nothing(
    stages: StageService, started: Ticket
) -> None:
    with pytest.raises(MoveRefusedError) as refused:
        await stages.move(started.id, "review", OWNER)

    assert str(refused.value) == f"{started.id} needs a commit on {started.branch} before Review"
    assert isinstance(refused.value, BadRequestError)
    assert (await stages.assess(started.id)).declared == ""


async def test_a_move_two_columns_on_is_refused_one_column_at_a_time(
    stages: StageService, started: Ticket
) -> None:
    with pytest.raises(
        MoveRefusedError, match=f"{started.id} moves one column at a time: Review is next"
    ):
        await stages.move(started.id, "merged", OWNER)


async def test_a_ticket_without_a_branch_is_told_how_to_get_one(
    stages: StageService, tickets: TicketService
) -> None:
    bare = await plain(tickets)

    with pytest.raises(MoveRefusedError) as refused:
        await stages.move(bare.id, "build", OWNER)

    assert str(refused.value) == (
        f"{bare.id} needs a branch before Build: "
        f"start an agent on it, or run code-factory start {bare.id}"
    )


async def test_released_is_what_a_release_gives_not_a_column_to_move_to(
    stages: StageService, started: Ticket
) -> None:
    with pytest.raises(BadRequestError, match=r"^unknown stage released$"):
        await stages.move(started.id, "released", OWNER)

    assert (await stages.assess(started.id)).declared == ""


async def test_a_move_whose_record_was_lost_is_recorded_when_the_move_is_made_again(
    stages: StageService,
    tickets: TicketService,
    activity: ActivityService,
    started: Ticket,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = tickets.record_activity
    failures = [True]

    async def flaky(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        if failures:
            failures.pop()
            msg = "the database blinked"
            raise RuntimeError(msg)
        return await real(*args, **kwargs)

    monkeypatch.setattr(tickets, "record_activity", flaky)
    with pytest.raises(RuntimeError, match="blinked"):
        await stages.move(started.id, "spec", OWNER)
    assert await last_stage_record(activity, started.id) == {"from": "spec", "to": "build"}

    again = await stages.move(started.id, "spec", OWNER)

    assert again.changed is False
    assert await last_stage_record(activity, started.id) == {"from": "build", "to": "spec"}


async def test_a_name_that_is_no_column_is_refused(stages: StageService, started: Ticket) -> None:
    with pytest.raises(BadRequestError, match=r"^unknown stage later$"):
        await stages.move(started.id, "later", OWNER)


async def test_a_ticket_that_does_not_exist_cannot_be_moved(stages: StageService) -> None:
    with pytest.raises(NotFoundError):
        await stages.move("CF-99999", "spec", OWNER)


async def test_a_move_forward_to_the_column_the_evidence_reached_is_allowed(
    stages: StageService, tickets: TicketService, started: Ticket, facts: FakeFacts
) -> None:
    pull = PullRequest(number=1, state=PullRequestState.OPEN, url="https://example.test/pull/1")
    await tickets.set_pull_request(started.id, pull, by=OWNER)
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe()
    await stages.move(started.id, "build", OWNER)

    moved = await stages.move(started.id, "review", OWNER)

    assert (moved.from_stage, moved.to_stage, moved.declared_after) == ("build", "review", "review")


async def test_a_move_is_recorded_though_the_latest_record_already_names_its_target(
    stages: StageService,
    tickets: TicketService,
    activity: ActivityService,
    started: Ticket,
    facts: FakeFacts,
) -> None:
    pull = PullRequest(number=1, state=PullRequestState.OPEN, url="https://example.test/pull/1")
    await tickets.set_pull_request(started.id, pull, by=OWNER)
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe()
    await stages.move(started.id, "build", OWNER)
    await tickets.record_activity(started.id, "stage", {"from": "build", "to": "review"}, by=OWNER)

    await stages.move(started.id, "review", OWNER)

    assert await last_stage_record(activity, started.id) == {"from": "build", "to": "review"}
    records = (await activity.list_activity(started.id, kinds=["stage"])).items
    assert [r.data.get("to") for r in records][-4:] == [
        "review",
        "build",
        "review",
        "review",
    ]


async def test_many_moves_are_all_or_nothing_and_name_every_refusal(
    stages: StageService, tickets: TicketService, started: Ticket
) -> None:
    bare, bare_too = await plain(tickets, "One"), await plain(tickets, "Two")

    with pytest.raises(MoveRefusedError) as refused:
        await stages.move_many([started.id, bare.id, bare_too.id], "build", OWNER)

    assert str(refused.value) == "; ".join(
        f"{b.id} needs a branch before Build: "
        f"start an agent on it, or run code-factory start {b.id}"
        for b in (bare, bare_too)
    )
    assert [(await stages.assess(t.id)).declared for t in (started, bare, bare_too)] == ["", "", ""]


async def test_moving_valid_tickets_together_equals_moving_them_one_by_one(
    stages: StageService, tickets: TicketService
) -> None:
    together = [await plain(tickets, f"T{n}") for n in range(2)]
    apart = [await plain(tickets, f"A{n}") for n in range(2)]

    moved = await stages.move_many([t.id for t in together], "spec", OWNER)
    singles = [await stages.move(t.id, "spec", OWNER) for t in apart]

    assert [(m.from_stage, m.to_stage, m.declared_after, m.changed) for m in moved] == [
        (m.from_stage, m.to_stage, m.declared_after, m.changed) for m in singles
    ]
    assert [(await stages.assess(t.id)).declared for t in together] == ["", ""]


async def test_nothing_acts_on_a_ticket_whose_git_facts_could_not_be_read(
    stages: StageService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe()
    facts.answers.clear()
    await stages.observe()

    with pytest.raises(UnavailableError, match=f"git facts of {started.id} are unknown"):
        await stages.move(started.id, "spec", OWNER)
    with pytest.raises(UnavailableError, match="are unknown"):
        await stages.is_reviewable(started.id)
    assert (await stages.assess(started.id)).declared == ""


async def test_a_ticket_whose_git_facts_were_read_may_be_moved_and_asked_about(
    stages: StageService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe()

    assert await stages.is_reviewable(started.id) is True
    assert (await stages.move(started.id, "spec", OWNER)).to_stage == "spec"
