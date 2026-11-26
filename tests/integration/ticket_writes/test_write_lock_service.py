"""Writes that really contend: a lock not got in time, and writes that must take turns.

Two sessions that really commit, since the savepoint fixture runs everything on one connection.
The repositories are named per test, so two runs on one schema never share a lock, and every
ticket they make is removed after.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import select, text

from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine, create_session_factory, lock_key
from code_factory.platform.errors import NotFoundError, UnavailableError
from code_factory.repositories.service import RepositoryService
from code_factory.tickets.models import TicketAddress, TicketFilter
from stage_fakes import FakeClock, FakeFacts
from write_fakes import Built, build
from write_values import exactly

OWNER = "owner:owner"
HANG = 60  # a hang guard, far above any load; the waits under test are the short ones below


@pytest.fixture
async def committed_uow(settings: Settings, migrated: None) -> AsyncGenerator[UnitOfWork]:  # noqa: ARG001
    engine = create_engine(settings)
    try:
        yield UnitOfWork(create_session_factory(engine))
    finally:
        await engine.dispose()


@pytest.fixture
def committed(committed_uow: UnitOfWork) -> Built:
    """A write service that gives a lock 0.2 seconds."""
    return build(committed_uow, FakeClock(), FakeFacts(), write_wait=0.2)


@pytest.fixture
async def patient(committed_uow: UnitOfWork) -> Built:
    """A write service that waits for a lock as long as a hang guard does."""
    return build(committed_uow, FakeClock(), FakeFacts(), write_wait=HANG)


@pytest.fixture
async def board(patient: Built, committed_uow: UnitOfWork, tmp_path: Path) -> AsyncGenerator[str]:
    """A tracked repository no other test uses; its tickets are deleted afterwards."""
    name = f"write-board-{uuid.uuid4().hex}"
    root = tmp_path / name
    root.mkdir()
    repositories = RepositoryService(committed_uow)
    await repositories.track(root)
    try:
        yield name
    finally:
        found = await patient.tickets.list(TicketFilter(repository=name, archived=None))
        numbers = [ticket.number for ticket in found]
        async with committed_uow() as session:
            # the writes committed offers of undo; every other test starts with none
            await session.execute(text("delete from undo_entries"))
            await session.execute(
                text("delete from ticket_links where ticket_number = any(:numbers)"),
                {"numbers": numbers},
            )
            await session.execute(
                text("update tickets set scratch = true where number = any(:numbers)"),
                {"numbers": numbers},
            )
        for ticket in found:
            await patient.tickets.delete_scratch(ticket.id)
        await repositories.untrack(root)


async def waiting(uow: UnitOfWork, repository: str, count: int) -> None:
    """Return once `count` sessions wait for the repository's write lock (read from pg_locks)."""
    waiters = text(
        "select count(*) from pg_locks where locktype = 'advisory' and not granted "
        "and classid = :high and objid = :low"
    )
    async with asyncio.timeout(HANG):
        while True:
            async with uow() as session:
                key = int(await session.scalar(select(lock_key(f"tickets:{repository}"))) or 0)
                high, low = (key >> 32) & 0xFFFFFFFF, key & 0xFFFFFFFF
                if int(await session.scalar(waiters, {"high": high, "low": low}) or 0) >= count:
                    return
            await asyncio.sleep(0.05)


async def test_a_write_waits_its_time_then_says_the_board_is_busy_and_changes_nothing(
    committed: Built,
) -> None:
    locked = TicketAddress(repository=f"write-lock-{uuid.uuid4().hex}", id="CF-999999")
    async with committed.tickets.unit([locked.repository], wait=1.0):
        with pytest.raises(UnavailableError, match=exactly("the board is busy; try again")):
            await committed.writes.set_rank(locked, 1, OWNER)

    with pytest.raises(NotFoundError, match=exactly("no such ticket")):
        await committed.writes.set_rank(locked, 1, OWNER)


async def test_five_creates_at_once_take_five_distinct_numbers(patient: Built, board: str) -> None:
    made = await asyncio.gather(
        *(patient.writes.create(board, {"title": f"T{n}"}, OWNER) for n in range(5))
    )

    assert len({ticket.id for ticket in made}) == 5


async def test_two_links_added_at_once_both_stay(
    patient: Built, board: str, committed_uow: UnitOfWork
) -> None:
    one = await patient.writes.create(board, {"title": "One"}, OWNER)
    two = await patient.writes.create(board, {"title": "Two"}, OWNER)
    own = await patient.writes.create(board, {"title": "Own"}, OWNER)
    async with patient.tickets.unit([board], wait=HANG):
        first = asyncio.create_task(patient.writes.add_link(own, "blocked_by", one.id, OWNER))
        second = asyncio.create_task(patient.writes.add_link(own, "blocked_by", two.id, OWNER))
        await waiting(committed_uow, board, 2)

    await asyncio.gather(first, second)

    assert sorted((await patient.tickets.get(own.id)).blocked_by) == sorted([one.id, two.id])
