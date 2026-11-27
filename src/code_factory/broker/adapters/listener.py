"""The run listener: a loopback socket served by uvicorn for the pure ASGI app of the broker."""

import asyncio
import contextlib
import socket
from collections.abc import Awaitable, Callable, Generator
from typing import Any, override

import uvicorn

from code_factory.platform.errors import UnavailableError

type ASGIApp = Callable[
    [dict[str, Any], Callable[[], Awaitable[Any]], Callable[[Any], Awaitable[None]]],
    Awaitable[None],
]

LIMIT_CONCURRENCY = 128
KEEP_ALIVE_S = 5
MAX_INCOMPLETE_EVENT = 16384
_POLL_S = 0.005


class _Server(uvicorn.Server):
    """A uvicorn server that leaves the process's signal handlers to the main server."""

    @override
    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None]:
        yield


class RunListener:
    """Serves `app` on `127.0.0.1` on a port of the system's choosing; never any other address."""

    def __init__(
        self, app: ASGIApp, *, shutdown_timeout_s: float, start_timeout_s: float = 10.0
    ) -> None:
        self._app = app
        self._shutdown_timeout_s = shutdown_timeout_s
        self._start_timeout_s = start_timeout_s
        self._server: _Server | None = None
        self._task: asyncio.Task[None] | None = None
        self._socket: socket.socket | None = None
        self.address: tuple[str, int] | None = None

    async def start(self) -> int:
        """Bind, serve and return the port once connections are accepted."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        config = uvicorn.Config(
            self._app,
            http="h11",
            ws="none",
            lifespan="off",
            log_level="critical",
            access_log=False,
            server_header=False,
            limit_concurrency=LIMIT_CONCURRENCY,
            timeout_keep_alive=KEEP_ALIVE_S,
            h11_max_incomplete_event_size=MAX_INCOMPLETE_EVENT,
            timeout_graceful_shutdown=int(self._shutdown_timeout_s) or 1,
        )
        server = _Server(config)
        self._server, self._socket = server, sock
        self._task = asyncio.create_task(server.serve(sockets=[sock]), name="broker-listener-serve")
        serving = False
        try:
            async with asyncio.timeout(self._start_timeout_s):
                while not server.started:
                    if self._task.done():
                        self._task.result()
                    await asyncio.sleep(_POLL_S)
            serving = True
        except TimeoutError:
            msg = "the key broker's listener did not start: another program may hold its port"
            raise UnavailableError(msg) from None
        finally:
            # A start that ends any other way (timed out, failed, cancelled) releases the socket
            # and ends the server; shielded so a cancellation cannot cut the release short.
            if not serving:
                await asyncio.shield(self.stop())
        port = int(sock.getsockname()[1])
        self.address = ("127.0.0.1", port)
        return port

    async def stop(self) -> None:
        """End the server, wait for it within the shutdown limit, and release the port."""
        server, task, sock = self._server, self._task, self._socket
        self._server = self._task = self._socket = None
        self.address = None
        if server is not None and task is not None:
            server.should_exit = True
            try:
                async with asyncio.timeout(self._shutdown_timeout_s):
                    await task
            except TimeoutError:
                server.force_exit = True
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        if sock is not None:
            sock.close()
