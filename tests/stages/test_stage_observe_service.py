"""The observer: git facts are stored, presence changes are appended once, an unreadable repository
keeps its old placement, and the loop survives a failing pass and stops when cancelled."""

import asyncio

import pytest

from code_factory.stages.models import ObserveReport
from code_factory.stages.service import StageService
from code_factory.tickets.models import NewTicket, Ticket
from code_factory.tickets.service import TicketService
from stage_fakes import FakeClock, FakeFacts
from stage_values import shape
from ticket_values import OWNER


async def second_ticket(tickets: TicketService, branch: str = "feat/CF-2") -> Ticket:
    made = await tickets.create(NewTicket(repository="sample", title="Second"), by=OWNER)
    return await tickets.set_branch(made.id, branch, by=OWNER)


def names(report: ObserveReport) -> list[tuple[str, bool]]:
    return [(c.stage, c.present) for c in report.changes]


async def test_the_first_pass_records_every_item_that_is_present_and_a_second_none(
    stages: StageService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True, pushed=True, has_commits=True)

    first = await stages.observe()
    second = await stages.observe()

    assert (first.observed, first.unknown) == (1, 0)
    assert names(first) == [("spec", True), ("build", True)]
    assert (second.observed, second.changes) == (1, [])


async def test_each_flip_of_an_item_is_one_row_and_the_rows_replay_to_the_checklist(
    stages: StageService, started: Ticket, facts: FakeFacts, clock: FakeClock
) -> None:
    steps = [
        {"local": True},
        {"local": True, "has_commits": True},
        {"local": True, "has_commits": False},
        {"local": True, "has_commits": True},
        {},
    ]
    flips = []
    for step in steps:
        facts.give(started.id, **step)
        clock.advance(10)
        flips.append(names(await stages.observe()))

    assert flips == [
        [("spec", True)],
        [("build", True)],
        [("build", False)],
        [("build", True)],
        [("spec", False), ("build", False)],
    ]
    rows = await stages.evidence_changes([started.id])
    final: dict[str, bool] = {}
    for row in rows:
        final[row.stage] = row.present
    items = (await stages.assess(started.id)).checklist
    assert {i.stage: final.get(i.stage, False) for i in items} == {
        i.stage: i.present for i in items
    }
    assert final == {"spec": False, "build": False}


async def test_a_git_read_that_failed_keeps_the_old_placement_and_loses_its_trust(
    stages: StageService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe()
    del facts.answers[started.id]

    report = await stages.observe()

    assert (report.observed, report.unknown, report.changes) == (0, 1, [])
    found = await stages.assess(started.id)
    assert not found.facts_known
    assert shape(found.checklist) == "PrPr-r-r-o"


async def test_a_repository_that_cannot_be_read_makes_its_tickets_unknown_not_the_pass_fail(
    stages: StageService, started: Ticket, facts: FakeFacts
) -> None:
    facts.failing = True

    report = await stages.observe()

    assert (report.observed, report.unknown) == (0, 1)
    assert not (await stages.assess(started.id)).facts_known


async def test_a_first_failed_read_keeps_the_placement_the_ticket_itself_gives(
    stages: StageService, started: Ticket, facts: FakeFacts
) -> None:
    facts.failing = True

    await stages.observe()

    found = await stages.assess(started.id)
    assert (found.stage, found.facts_known, found.observed_at) == ("build", False, None)


async def test_an_older_snapshot_that_lands_last_does_not_overwrite_a_newer_one(
    stages: StageService, started: Ticket, facts: FakeFacts, clock: FakeClock
) -> None:
    facts.give(started.id, local=True)
    gate = asyncio.Event()
    facts.hold = gate
    slow = asyncio.create_task(stages.observe([started.id]))
    async with asyncio.timeout(5):
        await facts.reading.get()
    clock.advance(10)
    facts.hold = None
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe([started.id])

    gate.set()
    await slow

    found = await stages.assess(started.id)
    assert found.checklist[1].present
    assert [(c.stage, c.present) for c in await stages.evidence_changes([started.id])] == [
        ("spec", True),
        ("build", True),
    ]


async def test_a_snapshot_of_a_branch_the_ticket_left_does_not_overwrite_the_new_branch(
    stages: StageService,
    tickets: TicketService,
    started: Ticket,
    facts: FakeFacts,
    clock: FakeClock,
) -> None:
    facts.give(started.id, local=True)
    gate = asyncio.Event()
    facts.hold = gate
    slow = asyncio.create_task(stages.observe([started.id]))
    async with asyncio.timeout(5):
        await facts.reading.get()
    clock.advance(10)
    facts.hold = None
    await tickets.set_branch(started.id, "feat/CF-1-again", by=OWNER)
    facts.give(started.id, local=True, pushed=True, has_commits=True)
    await stages.observe([started.id])

    gate.set()
    await slow

    found = await stages.assess(started.id)
    assert found.checklist[1].present
    assert [(c.stage, c.present) for c in await stages.evidence_changes([started.id])] == [
        ("spec", True),
        ("build", True),
    ]


async def test_named_tickets_only_are_observed(
    stages: StageService, tickets: TicketService, started: Ticket, facts: FakeFacts
) -> None:
    other = await second_ticket(tickets)
    facts.give(started.id, local=True)
    facts.give(other.id, local=True)

    report = await stages.observe([other.id])

    assert [c.ticket_id for c in report.changes] == [other.id]
    assert (await stages.assess(started.id)).observed_at is None
    assert (await stages.assess(other.id)).observed_at is not None


async def test_a_landed_ticket_is_read_again_only_after_an_hour(
    stages: StageService, started: Ticket, facts: FakeFacts, clock: FakeClock
) -> None:
    facts.give(started.id, local=True, merged=True)
    await stages.observe()
    assert len(facts.calls) == 1

    clock.advance(59 * 60)
    await stages.observe()
    assert len(facts.calls) == 1

    clock.advance(60)
    await stages.observe()
    assert len(facts.calls) == 2


async def test_a_ticket_not_landed_is_read_every_pass(
    stages: StageService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True)

    await stages.observe()
    await stages.observe()

    assert len(facts.calls) == 2


async def test_the_observer_runs_a_pass_then_waits_and_stops_when_told(
    stages: StageService, started: Ticket, facts: FakeFacts
) -> None:
    facts.give(started.id, local=True)
    stop = asyncio.Event()
    task = asyncio.create_task(stages.run_observer(0.02, stop))
    async with asyncio.timeout(5):
        await facts.seen.get()
        await facts.seen.get()
    stop.set()
    async with asyncio.timeout(5):
        await task

    assert len(facts.calls) >= 2


async def test_the_observer_survives_a_failing_pass(
    stages: StageService, monkeypatch: pytest.MonkeyPatch
) -> None:
    passes = 0
    seen: asyncio.Queue[int] = asyncio.Queue()

    async def observe(_ids: object = None) -> ObserveReport:
        nonlocal passes
        passes += 1
        seen.put_nowait(passes)
        if passes == 1:
            msg = "the database blinked"
            raise RuntimeError(msg)
        return ObserveReport()

    monkeypatch.setattr(stages, "observe", observe)
    stop = asyncio.Event()
    task = asyncio.create_task(stages.run_observer(0.02, stop))
    async with asyncio.timeout(5):
        for _ in range(3):
            await seen.get()
    stop.set()
    await task

    assert passes >= 3


async def test_cancelling_the_observer_ends_it_as_cancelled(stages: StageService) -> None:
    task = asyncio.create_task(stages.run_observer(3600))
    await asyncio.sleep(0.05)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert task.cancelled()


async def test_a_pass_over_every_ticket_leaves_an_archived_one_alone(
    stages: StageService, tickets: TicketService, started: Ticket, facts: FakeFacts
) -> None:
    gone = await second_ticket(tickets)
    await tickets.archive(gone.id, by=OWNER)
    facts.give(started.id, local=True)
    facts.give(gone.id, local=True)

    report = await stages.observe()

    assert report.observed == 1
    assert {c.ticket_id for c in report.changes} == {started.id}


async def test_an_archived_ticket_named_by_id_is_still_observed(
    stages: StageService, tickets: TicketService, facts: FakeFacts
) -> None:
    gone = await second_ticket(tickets)
    await tickets.archive(gone.id, by=OWNER)
    facts.give(gone.id, local=True)

    assert (await stages.observe([gone.id])).observed == 1
