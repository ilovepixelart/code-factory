"""The undo store through its service, against the test database.

Oracle: the ticket-writes spec (section 6, `UndoService`, and its tests 34 to 41): an entry is
claimed once, within 30 seconds, survives a restart, and is consumed even when its handler refuses.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, override

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import ConflictError, GoneError
from code_factory.undo.models import Changed
from code_factory.undo.service import UndoService

START = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
GONE = "nothing to undo any more"


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class Calls:
    """A handler that records what it was given."""

    def __init__(self) -> None:
        self.seen: list[tuple[dict[str, Any], str]] = []

    async def __call__(self, payload: dict[str, Any], by: str) -> None:
        self.seen.append((payload, by))


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def undo(uow: UnitOfWork, clock: Clock) -> UndoService:
    return UndoService(uow, clock=clock)


@pytest.fixture
def calls(undo: UndoService) -> Calls:
    handler = Calls()
    undo.register("test.revert", handler)
    return handler


@pytest.mark.usefixtures("calls")
async def test_an_offer_answers_its_notice_and_a_32_hex_token(undo: UndoService) -> None:
    changed = await undo.offer("test.revert", {"ops": []}, "Archived CF-2")
    assert changed.notice == "Archived CF-2"
    assert changed.undo is not None
    assert len(changed.undo) == 32
    assert set(changed.undo) <= set("0123456789abcdef")


async def test_undo_runs_the_kinds_handler_with_the_stored_payload_and_the_caller(
    undo: UndoService, calls: Calls
) -> None:
    payload = {"ops": [{"op": "fields", "id": "CF-2", "to": {"title": "Old"}, "n": 3}]}
    offered = await undo.offer("test.revert", payload, "Saved CF-2")
    assert offered.undo is not None
    answer = await undo.undo(offered.undo, "owner")
    assert answer == Changed(notice="", undo=None)
    assert calls.seen == [(payload, "owner")]


async def test_a_token_works_once(undo: UndoService, calls: Calls) -> None:
    offered = await undo.offer("test.revert", {}, "n")
    token = offered.undo or ""
    await undo.undo(token, "owner")
    with pytest.raises(GoneError, match=GONE):
        await undo.undo(token, "owner")
    assert len(calls.seen) == 1


async def test_an_unknown_token_is_gone(undo: UndoService, calls: Calls) -> None:
    with pytest.raises(GoneError, match=GONE):
        await undo.undo("0" * 32, "owner")
    assert calls.seen == []


async def test_an_entry_still_works_at_exactly_thirty_seconds(
    undo: UndoService, calls: Calls, clock: Clock
) -> None:
    token = (await undo.offer("test.revert", {}, "n")).undo or ""
    clock.now = START + timedelta(seconds=30)
    await undo.undo(token, "owner")
    assert len(calls.seen) == 1


async def test_an_entry_is_gone_one_millisecond_after_thirty_seconds_and_runs_nothing(
    undo: UndoService, calls: Calls, clock: Clock
) -> None:
    token = (await undo.offer("test.revert", {}, "n")).undo or ""
    clock.now = START + timedelta(seconds=30, milliseconds=1)
    with pytest.raises(GoneError, match=GONE):
        await undo.undo(token, "owner")
    assert calls.seen == []


async def test_a_handler_that_refuses_still_consumes_the_token(undo: UndoService) -> None:
    async def refuse(_payload: dict[str, Any], _by: str) -> None:
        msg = "CF-2 title changed since"
        raise ConflictError(msg)

    undo.register("test.refuse", refuse)
    token = (await undo.offer("test.refuse", {}, "n")).undo or ""
    with pytest.raises(ConflictError, match="CF-2 title changed since"):
        await undo.undo(token, "owner")
    with pytest.raises(GoneError, match=GONE):
        await undo.undo(token, "owner")


async def test_an_entry_of_a_kind_nobody_handles_is_gone(uow: UnitOfWork, clock: Clock) -> None:
    before = UndoService(uow, clock=clock)
    before.register("old.kind", Calls())
    offered = await before.offer("old.kind", {}, "n")
    fresh = UndoService(uow, clock=clock)
    with pytest.raises(GoneError, match=GONE):
        await fresh.undo(offered.undo or "", "owner")


async def test_an_entry_survives_a_restart(uow: UnitOfWork, clock: Clock) -> None:
    first = UndoService(uow, clock=clock)
    first.register("test.revert", Calls())
    token = (await first.offer("test.revert", {"a": 1}, "n")).undo or ""
    after = UndoService(uow, clock=clock)
    handler = Calls()
    after.register("test.revert", handler)
    await after.undo(token, "owner")
    assert handler.seen == [({"a": 1}, "owner")]


async def test_a_kind_registered_twice_is_a_programming_error(
    undo: UndoService, calls: Calls
) -> None:
    with pytest.raises(ValueError, match=r"undo kind test\.revert is registered already"):
        undo.register("test.revert", calls)


async def test_a_blank_kind_is_refused_on_register_and_on_offer(undo: UndoService) -> None:
    with pytest.raises(ValueError, match="an undo kind is not blank"):
        undo.register("", Calls())
    with pytest.raises(ValueError, match="an undo kind is not blank"):
        await undo.offer("", {}, "n")


@pytest.mark.usefixtures("calls")
async def test_a_sweep_removes_entries_expired_more_than_a_minute_and_counts_them(
    undo: UndoService, clock: Clock
) -> None:
    old = (await undo.offer("test.revert", {}, "old")).undo or ""
    clock.now = START + timedelta(seconds=10)
    recent = (await undo.offer("test.revert", {}, "recent")).undo or ""
    clock.now = START + timedelta(seconds=30 + 60 + 1)  # `old` expired 61 s ago, `recent` 51 s
    assert await undo.sweep() == 1
    assert await undo.sweep() == 0
    # `recent` is expired, so it is Gone, but the sweep left it for its own claim to consume.
    with pytest.raises(GoneError, match=GONE):
        await undo.undo(recent, "owner")
    with pytest.raises(GoneError, match=GONE):
        await undo.undo(old, "owner")


@pytest.mark.usefixtures("calls")
async def test_a_sweep_keeps_an_entry_expired_exactly_a_minute_ago(
    undo: UndoService, clock: Clock
) -> None:
    await undo.offer("test.revert", {}, "n")
    clock.now = START + timedelta(seconds=90)
    assert await undo.sweep() == 0
    clock.now = START + timedelta(seconds=90, milliseconds=1)
    assert await undo.sweep() == 1


async def test_a_sweep_keeps_a_live_entry(undo: UndoService, calls: Calls) -> None:
    token = (await undo.offer("test.revert", {}, "n")).undo or ""
    assert await undo.sweep() == 0
    await undo.undo(token, "owner")
    assert len(calls.seen) == 1


class FailsOnce:
    """A unit of work whose first use fails, as a dropped connection would."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self.uses = 0

    def __call__(self):  # noqa: ANN204
        self.uses += 1
        if self.uses == 1:
            msg = "connection dropped"
            raise OSError(msg)
        return self._uow()


async def test_the_sweeper_survives_a_failed_pass_and_stops_on_cancel(
    uow: UnitOfWork, clock: Clock
) -> None:
    flaky = FailsOnce(uow)
    undo = UndoService(flaky, clock=clock)  # ty: ignore[invalid-argument-type]  # stands in for the unit of work
    task = asyncio.create_task(undo.run_sweeper(interval=0.01))
    async with asyncio.timeout(5):
        while flaky.uses < 3:  # noqa: ASYNC110  # polling a counter the task bumps
            await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_the_window_starts_once_the_connection_is_held(
    connection: AsyncConnection, clock: Clock
) -> None:
    class SlowPool(AsyncSession):
        """A session whose connection checkout waits 9 s, as a busy pool would."""

        @override
        async def connection(self, *args: Any, **kwargs: Any) -> AsyncConnection:
            clock.now += timedelta(seconds=9)
            return await super().connection(*args, **kwargs)

    sessions = async_sessionmaker(
        bind=connection,
        class_=SlowPool,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    units = UnitOfWork(sessions)  # ty: ignore[invalid-argument-type]  # a session subclass is an AsyncSession
    undo = UndoService(units, clock=clock)
    undo.register("test.revert", Calls())
    token = (await undo.offer("test.revert", {}, "n")).undo or ""
    clock.now = START + timedelta(seconds=30)  # held 9 s later: 30 s after the offer's connection
    await undo.undo(token, "owner")


async def test_undo_credits_the_caller_it_was_given(undo: UndoService, calls: Calls) -> None:
    token = (await undo.offer("test.revert", {}, "n")).undo or ""
    await undo.undo(token, "agent-7")
    assert [by for _payload, by in calls.seen] == ["agent-7"]


async def test_an_offer_of_a_kind_with_no_handler_is_refused_and_stores_nothing(
    undo: UndoService, uow: UnitOfWork
) -> None:
    with pytest.raises(ValueError, match=r"undo kind tickets\.revrt has no handler"):
        await undo.offer("tickets.revrt", {}, "n")
    async with uow() as session:
        count = await session.scalar(text("SELECT count(*) FROM undo_entries"))
    assert count == 0


@pytest.mark.usefixtures("calls")
async def test_the_sweeper_deletes_an_expired_entry(
    uow: UnitOfWork, undo: UndoService, clock: Clock
) -> None:
    await undo.offer("test.revert", {}, "n")
    clock.now = START + timedelta(seconds=91)
    swept = asyncio.Event()

    async def sweep_and_signal() -> int:
        gone = await UndoService.sweep(undo)
        swept.set()
        return gone

    undo.sweep = sweep_and_signal  # observe the sweeper's pass
    task = asyncio.create_task(undo.run_sweeper(interval=60))
    async with asyncio.timeout(5):
        await swept.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with uow() as session:
        assert await session.scalar(text("SELECT count(*) FROM undo_entries")) == 0


@pytest.mark.usefixtures("calls")
async def test_an_entry_stores_when_it_was_offered(undo: UndoService, uow: UnitOfWork) -> None:
    await undo.offer("test.revert", {}, "n")
    async with uow() as session:
        row = (await session.execute(text("SELECT created_at, expires_at FROM undo_entries"))).one()
    assert (row.created_at, row.expires_at) == (START, START + timedelta(seconds=30))


async def test_the_window_is_read_before_the_claim_commits(
    connection: AsyncConnection, clock: Clock
) -> None:
    class SlowCommit(AsyncSession):
        """A session whose commit takes 1 s, as a loaded database would."""

        @override
        async def commit(self) -> None:
            clock.now += timedelta(seconds=1)
            await super().commit()

    sessions = async_sessionmaker(
        bind=connection,
        class_=SlowCommit,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    units = UnitOfWork(sessions)  # ty: ignore[invalid-argument-type]  # a session subclass is an AsyncSession
    undo = UndoService(units, clock=clock)
    handler = Calls()
    undo.register("test.revert", handler)
    token = (await undo.offer("test.revert", {}, "n")).undo or ""
    clock.now = START + timedelta(seconds=30)  # the click lands on the last instant
    await undo.undo(token, "owner")
    assert len(handler.seen) == 1
