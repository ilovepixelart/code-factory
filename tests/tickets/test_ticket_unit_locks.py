"""A unit holds a lock per repository it names; one that cannot get it in time says the board is
busy. Two units on separate connections that really commit.

The locks are advisory locks keyed by schema; every test names its repositories afresh, so a
name shared with another run on the same schema never makes this one wait."""

import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine, create_session_factory, lock_key
from code_factory.platform.errors import UnavailableError
from code_factory.tickets.service import TicketService

# How long a test lets a lock holder or a waiter take before it gives up: far above any load, since
# only a hang reaches it, and below pytest's own timeout (pyproject.toml) so this one fails first.
GIVE_UP_S = 20.0

WAITING_FOR_LOCK = text(
    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted "
    "AND (classid::bigint << 32) | objid::bigint = :key"
)


def fresh(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def engine(settings: Settings, migrated: None) -> AsyncGenerator[AsyncEngine]:  # noqa: ARG001
    engine = create_engine(settings)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def committed(engine: AsyncEngine) -> TicketService:
    return TicketService(UnitOfWork(create_session_factory(engine)))


async def _is_waiting(engine: AsyncEngine, repository: str) -> None:
    """Return once a transaction waits for the repository's lock: the database says so."""
    async with engine.connect() as connection:
        key = await connection.scalar(select(lock_key(f"tickets:{repository}")))
        while not await connection.scalar(WAITING_FOR_LOCK, {"key": key}):  # noqa: ASYNC110  # polls the database's own lock table
            await asyncio.sleep(0.01)


async def test_a_unit_waits_its_time_for_a_repository_and_then_says_the_board_is_busy(
    committed: TicketService,
) -> None:
    first, second = fresh("lock-a"), fresh("lock-b")
    async with committed.unit([first, second], wait=GIVE_UP_S):
        with pytest.raises(UnavailableError, match="the board is busy; try again"):
            async with committed.unit([second], wait=0.2):
                pytest.fail("the lock was not held")


async def test_a_unit_of_another_repository_is_not_blocked(committed: TicketService) -> None:
    held, other = fresh("lock-a"), fresh("lock-c")
    async with (
        committed.unit([held], wait=GIVE_UP_S),
        asyncio.timeout(GIVE_UP_S),
        committed.unit([other], wait=GIVE_UP_S),
    ):
        pass


async def test_a_unit_gets_the_repository_once_the_holder_is_done(
    committed: TicketService, engine: AsyncEngine
) -> None:
    repository = fresh("lock-d")
    held, release = asyncio.Event(), asyncio.Event()
    holder_finished = asyncio.Event()

    async def hold() -> None:
        async with committed.unit([repository], wait=GIVE_UP_S):
            held.set()
            await release.wait()
            holder_finished.set()

    # The group ends every task when the body fails, and raises what a task raised: a holder or an
    # observer that failed is never mistaken for a lock that was seen.
    async with asyncio.timeout(GIVE_UP_S), asyncio.TaskGroup() as group:
        group.create_task(hold())
        await held.wait()
        waiter = group.create_task(_enter(committed, repository, holder_finished))
        observer = group.create_task(_is_waiting(engine, repository))
        await asyncio.wait({waiter, observer}, return_when=asyncio.FIRST_COMPLETED)
        assert not waiter.done(), "the second unit got the lock while the first held it"
        release.set()
        assert await waiter is True


async def _enter(committed: TicketService, repository: str, holder_finished: asyncio.Event) -> bool:
    """Take the repository's lock; whether the holder had finished by then."""
    async with committed.unit([repository], wait=GIVE_UP_S):
        return holder_finished.is_set()
