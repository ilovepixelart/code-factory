"""The container's turn: rows wait their order, and a row waits only when it is in the queue."""

import asyncio
from pathlib import Path

from checks_support import REPO, Clock, container_config, write_config
from code_factory.checks.models import RunState, Verdict
from code_factory.checks.repository import CheckStore
from code_factory.checks.service import CheckService
from code_factory.platform.db import UnitOfWork
from code_factory.tickets.models import Ticket


async def test_a_row_queued_before_the_container_was_configured_still_gets_its_turn(
    checks: CheckService, started: Ticket, root: Path, engine: Path
) -> None:
    write_config(root, "[checks]\ncommand = 'true'\n")
    check_id = await checks.start(started.id)
    write_config(root, container_config(engine))
    row = await asyncio.wait_for(checks.run_now(check_id), timeout=20)
    assert (row.state, row.verdict, row.contained.value) == (
        RunState.FINISHED,
        Verdict.PASSED,
        "container",
    )


async def queued(store: CheckStore, subject: str, clock: Clock) -> int:
    row = await store.runs.insert(
        {
            "repository": REPO,
            "subject": subject,
            "scope": "reached",
            "commit": "a" * 40,
            "tree_id": "b" * 40,
            "state": "queued",
            "contained": "container",
            "owner": "me",
            "requested_by": "alex",
            "queued_at": clock.now,
            "beat_at": clock.now,
        }
    )
    assert row is not None
    return row.id


async def test_with_one_slot_the_older_container_row_runs_first_and_the_newer_waits(
    uow: UnitOfWork, clock: Clock
) -> None:
    async with uow() as session:
        store = CheckStore(session)
        older = await queued(store, "CF-1", clock)
        newer = await queued(store, "CF-2", clock)
        assert not await store.runs.take_turn(newer, 1, clock.now)
        assert await store.runs.take_turn(older, 1, clock.now)
        assert not await store.runs.take_turn(newer, 1, clock.now)
        await store.runs.finish(older, clock.now, Verdict.PASSED, {})
        assert await store.runs.take_turn(newer, 1, clock.now)


async def test_with_two_slots_both_container_rows_run_and_a_third_waits(
    uow: UnitOfWork, clock: Clock
) -> None:
    async with uow() as session:
        store = CheckStore(session)
        ids = [await queued(store, f"CF-{n}", clock) for n in (1, 2, 3)]
        assert [await store.runs.take_turn(i, 2, clock.now) for i in ids[:2]] == [True, True]
        assert not await store.runs.take_turn(ids[2], 2, clock.now)


async def test_a_running_row_unbeaten_for_a_minute_gives_its_slot_to_the_next(
    uow: UnitOfWork, clock: Clock
) -> None:
    async with uow() as session:
        store = CheckStore(session)
        older = await queued(store, "CF-1", clock)
        newer = await queued(store, "CF-2", clock)
        assert await store.runs.take_turn(older, 1, clock.now)
        clock.after(seconds=59)
        assert not await store.runs.take_turn(newer, 1, clock.now)
        clock.after(seconds=2)
        assert await store.runs.beat(newer, "me", clock.now)
        assert await store.runs.take_turn(newer, 1, clock.now)
