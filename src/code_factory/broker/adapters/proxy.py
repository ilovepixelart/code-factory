"""The run proxy: a CONNECT filter on loopback so a container run reaches only its model host."""

import asyncio
import contextlib
import logging
from collections import deque

from code_factory.broker.models import Connect
from code_factory.broker.rules.connect import MAX_HEAD, parse_connect

logger = logging.getLogger(__name__)

MAX_REFUSALS = 100
_CHUNK = 64 * 1024
_REASONS = {200: "Connection Established", 403: "Forbidden", 405: "Method Not Allowed"}
_REASONS |= {502: "Bad Gateway", 503: "Service Unavailable"}


class _TunnelEnded(Exception):  # noqa: N818  # a signal between the two copy tasks, not an error
    """One side of a tunnel finished: the other is ended with it."""


def _status_line(status: int, note: str = "") -> bytes:
    body = note.encode()
    head = f"HTTP/1.1 {status} {_REASONS[status]}\r\nContent-Length: {len(body)}\r\n"
    return f"{head}Connection: close\r\n\r\n".encode() + body


class RunProxyServer:
    """Accepts `CONNECT host:port` for the allowed list only, then relays bytes both ways."""

    def __init__(  # the limits of one proxy
        self,
        allowed: list[str],
        *,
        head_timeout_s: float = 10.0,
        connect_timeout_s: float = 10.0,
        idle_s: float = 900.0,
        max_tunnels: int = 64,
    ) -> None:
        self._allowed = allowed
        self._head_timeout_s = head_timeout_s
        self._connect_timeout_s = connect_timeout_s
        self._idle_s = idle_s
        self._max_tunnels = max_tunnels
        self._server: asyncio.Server | None = None
        self._live: set[asyncio.Task[None]] = set()
        self._tunnels = 0
        self.refusals: deque[str] = deque(maxlen=MAX_REFUSALS)
        self.address = ""

    async def start(self) -> str:
        """Listen on `127.0.0.1` on a free port; the `host:port` to give a run."""
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0, limit=MAX_HEAD + 1)
        host, port = self._server.sockets[0].getsockname()[:2]
        self.address = f"{host}:{port}"
        return self.address

    async def stop(self) -> None:
        """Close the listener and every tunnel."""
        if self._server is not None:
            self._server.close()
        for task in list(self._live):
            task.cancel()
        await asyncio.gather(*self._live, return_exceptions=True)
        if self._server is not None:
            await self._server.wait_closed()
            self._server = None

    def _refuse(self, status: int, target: str, reason: str) -> None:
        self.refusals.append(f"{status} {target}: {reason}")
        logger.warning("run proxy refused %r: %s", target, reason)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._live.add(task)
        try:
            await self._serve(reader, writer)
        except OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError:
            pass  # the peer went away or sent too much: the connection closes with no relay
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
            if task is not None:
                self._live.discard(task)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async with asyncio.timeout(self._head_timeout_s):
            head = await reader.readuntil(b"\r\n\r\n")
        parsed = parse_connect(head, self._allowed)
        if not isinstance(parsed, Connect):
            if parsed.status:
                self._refuse(
                    parsed.status, head[:80].decode("latin-1").split("\r\n")[0], parsed.reason
                )
                writer.write(_status_line(parsed.status, parsed.reason))
                await writer.drain()
            return
        if self._tunnels >= self._max_tunnels:
            self._refuse(503, parsed.target, "too many tunnels")
            writer.write(_status_line(503, "too many tunnels"))
            await writer.drain()
            return
        self._tunnels += 1
        try:
            await self._tunnel(parsed.target, reader, writer)
        finally:
            self._tunnels -= 1

    async def _tunnel(
        self, target: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        host, _, port = target.rpartition(":")
        try:
            async with asyncio.timeout(self._connect_timeout_s):
                out_reader, out_writer = await asyncio.open_connection(host, int(port))
        except OSError, TimeoutError:
            writer.write(_status_line(502, "the host did not answer"))
            await writer.drain()
            return
        try:
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await self._relay(reader, writer, out_reader, out_writer)
        finally:
            out_writer.close()
            with contextlib.suppress(OSError):
                await out_writer.wait_closed()

    async def _relay(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        out_reader: asyncio.StreamReader,
        out_writer: asyncio.StreamWriter,
    ) -> None:
        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(self._copy(reader, out_writer))
                group.create_task(self._copy(out_reader, writer))
        except* _TunnelEnded, OSError, TimeoutError:
            pass  # one side ended or went idle: the group has cancelled the other

    async def _copy(self, source: asyncio.StreamReader, sink: asyncio.StreamWriter) -> None:
        while True:
            async with asyncio.timeout(self._idle_s):
                data = await source.read(_CHUNK)
            if not data:
                raise _TunnelEnded
            sink.write(data)
            await sink.drain()
