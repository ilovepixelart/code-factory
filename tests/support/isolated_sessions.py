"""Sessions on a test's one isolated connection, each a savepoint, taking turns across tasks."""

import asyncio
from typing import Self, override

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker


class _Turns:
    """Whose turn it is on the test's one connection: one task at a time, as often as it nests."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task[object] | None = None
        self._depth = 0

    async def take(self) -> None:
        task = asyncio.current_task()
        if self._owner is not task:
            await self._lock.acquire()
            self._owner = task
        self._depth += 1

    def give(self) -> None:
        self._depth -= 1
        if self._depth == 0:
            self._owner = None
            self._lock.release()


class _TurnSession(AsyncSession):
    """A session on the test's one connection; sessions of concurrent tasks take turns.

    A service may read in parallel (the team fans out over the runs). On their own connections in
    the app that is safe; here every session is a savepoint of one connection, which two tasks
    must not interleave.
    """

    @override
    async def __aenter__(self) -> Self:
        await self.info[_TURNS].take()
        return await super().__aenter__()

    @override
    async def __aexit__(self, type_: object, value: object, traceback: object) -> None:
        try:
            await super().__aexit__(type_, value, traceback)
        finally:
            self.info[_TURNS].give()


_TURNS = "turns"


def isolated_sessions(connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    """Sessions on `connection`: each a savepoint of its transaction, one task at a time."""
    return async_sessionmaker(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        class_=_TurnSession,
        info={_TURNS: _Turns()},
    )
