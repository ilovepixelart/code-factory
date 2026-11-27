"""The one way a service reaches the database: a unit of work per use case."""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

import asyncpg
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.errors import DatabaseUnavailableError, SettingsError

_CONNECTING = (ConnectionError, asyncpg.CannotConnectNowError, asyncpg.ConnectionDoesNotExistError)


def connection_lost(error: BaseException) -> bool:
    """Whether the error is the database being out of reach, not anything the use case did."""
    if isinstance(error, _CONNECTING):
        return True
    if isinstance(error, DBAPIError):
        return error.connection_invalidated or isinstance(error.orig, _CONNECTING)
    return False


class UnitOfWork:
    """Hands a service one session per use case and commits it when the use case ends.

    HTTP routes, MCP tools, the CLI and background tasks all reach a service, and the service
    opens the unit of work, so the commit happens inside the call: a failed commit is an
    exception the caller answers, never a response already sent. An exception leaves the block
    without committing and the session rolls back.
    """

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[AsyncSession]:
        """Yield a session; commit when the block ends normally, roll back when it raises."""
        try:
            async with self._session_factory() as session:
                yield session
                await session.commit()
        except Exception as error:
            if not connection_lost(error):
                raise
            lines = str(error).splitlines()
            first = lines[0][:200] if lines else ""
            msg = f"the database is not reachable ({type(error).__name__}: {first})"
            raise DatabaseUnavailableError(msg) from error


def _refuse() -> AsyncSession:
    msg = "this command runs without a database, so it cannot read or write one"
    raise SettingsError(msg)


class NoDatabase(UnitOfWork):
    """The unit of work of a command that runs without a database: every use refuses."""

    def __init__(self) -> None:
        super().__init__(_refuse)
