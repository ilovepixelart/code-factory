"""The one dedicated connection that listens for new events, kept alive across restarts."""

import asyncio
import logging
from collections.abc import Callable

import asyncpg

logger = logging.getLogger(__name__)

FIRST_RETRY_S = 0.5
LAST_RETRY_S = 10.0
CALL_TIMEOUT_S = 5.0
PING_EVERY_S = 30.0
CLOSE_TIMEOUT_S = 2.0
APPLICATION_NAME = "code_factory_sessions_listen"


class ListenConnection:
    """`LISTEN` on a channel over a connection of its own, not from the pool.

    `on_wake` runs on every notification and after every (re)connection, so a reader does a
    catch-up read and a notification lost while the connection was down costs nothing.
    """

    def __init__(self, dsn: str, channel: str, on_wake: Callable[[], None]) -> None:
        self._dsn = dsn
        self._channel = channel
        self._on_wake = on_wake

    @staticmethod
    def application_name(channel: str) -> str:
        """What the listener's connection calls itself, so it can be told from the others."""
        return f"{APPLICATION_NAME}_{channel}"

    async def run(self) -> None:
        """Listen until cancelled; a lost connection is opened again with a growing pause."""
        pause = FIRST_RETRY_S
        while True:
            try:
                await self._listen_once()
                pause = FIRST_RETRY_S
            except OSError, asyncpg.PostgresError, asyncpg.InterfaceError:
                logger.warning("the session listener lost its connection; retrying", exc_info=True)
            await asyncio.sleep(pause)
            pause = min(pause * 2, LAST_RETRY_S)

    async def _listen_once(self) -> None:
        async with asyncio.timeout(CALL_TIMEOUT_S):
            connection = await asyncpg.connect(
                self._dsn,
                timeout=CALL_TIMEOUT_S,
                server_settings={"application_name": self.application_name(self._channel)},
            )
        closed = asyncio.Event()
        try:
            connection.add_termination_listener(lambda _connection: closed.set())
            async with asyncio.timeout(CALL_TIMEOUT_S):
                await connection.add_listener(self._channel, lambda *_args: self._on_wake())
            self._on_wake()
            while not closed.is_set():
                try:
                    await asyncio.wait_for(closed.wait(), PING_EVERY_S)
                except TimeoutError:
                    async with asyncio.timeout(CALL_TIMEOUT_S):
                        await connection.execute("select 1")
        finally:
            closing = asyncio.create_task(self._close(connection))
            await asyncio.shield(closing)

    @staticmethod
    async def _close(connection: asyncpg.Connection) -> None:
        try:
            async with asyncio.timeout(CLOSE_TIMEOUT_S):
                await connection.close()
        except OSError, asyncpg.PostgresError, asyncpg.InterfaceError:
            connection.terminate()
