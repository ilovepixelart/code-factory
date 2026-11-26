"""Helpers of the broker tests: a stand-in provider on a real loopback socket, and fakes."""

import asyncio
import socket
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import uvicorn

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


@dataclass
class Seen:
    """One request the stand-in received, as it arrived."""

    method: str
    target: str
    headers: list[tuple[str, str]]
    body: bytes = b""
    closed: asyncio.Event = field(default_factory=asyncio.Event)

    def header(self, name: str) -> list[str]:
        return [value for key, value in self.headers if key == name.lower()]

    def everything(self) -> bytes:
        """Every byte of the request in one blob, for a search for what must not be there."""
        head = f"{self.method} {self.target}\n" + "\n".join(f"{k}: {v}" for k, v in self.headers)
        return head.encode("latin-1") + b"\n" + self.body


Handler = Callable[[Seen, Receive, Send], Awaitable[None]]


async def reply(
    send: Send,
    status: int = 200,
    body: bytes = b'{"ok": true}',
    headers: list[tuple[str, str]] | None = None,
) -> None:
    sent = [(b"content-type", b"application/json")]
    sent += [(k.encode(), v.encode()) for k, v in headers or []]
    await send({"type": "http.response.start", "status": status, "headers": sent})
    await send({"type": "http.response.body", "body": body})


async def read_all(receive: Receive) -> bytes:
    data = b""
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return data
        data += bytes(message.get("body", b""))
        if not message.get("more_body"):
            return data


async def answer_ok(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
    await reply(send)


async def stream_forever(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
    """A 200 that sends a little every 50 ms until the client's connection is gone."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    while True:
        await send({"type": "http.response.body", "body": b"x" * 100, "more_body": True})
        try:
            message = await asyncio.wait_for(receive(), 0.05)
        except TimeoutError:
            continue
        if message["type"] == "http.disconnect":
            return


class StandIn:
    """A provider on 127.0.0.1 that records every request and answers through `handler`."""

    def __init__(self, handler: Handler = answer_ok) -> None:
        self.handler = handler
        self.seen: list[Seen] = []
        self.port = 0
        self.live = 0

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        raw = bytes(scope["raw_path"])
        query = bytes(scope["query_string"])
        target = (raw + (b"?" + query if query else b"")).decode("latin-1")
        headers = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in scope["headers"]]
        seen = Seen(str(scope["method"]), target, headers)
        self.seen.append(seen)
        self.live += 1
        try:
            await self.handler(seen, receive, send)
        finally:
            self.live -= 1
            seen.closed.set()


@asynccontextmanager
async def stand_in(handler: Handler = answer_ok) -> AsyncGenerator[StandIn]:
    """Run a stand-in provider until the block ends."""
    app = StandIn(handler)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    app.port = sock.getsockname()[1]
    config = uvicorn.Config(app, lifespan="off", log_level="critical", access_log=False)
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        if task.done():
            task.result()
        await asyncio.sleep(0.005)
    try:
        yield app
    finally:
        server.should_exit = True
        server.force_exit = True
        await task
        sock.close()


@dataclass
class Reply:
    """An answer read off a raw socket."""

    status: int
    headers: list[tuple[str, str]]
    body: bytes

    def header(self, name: str) -> list[str]:
        return [value for key, value in self.headers if key == name.lower()]


async def raw_http(
    port: int, method: str, target: str, headers: list[tuple[str, str]], body: bytes = b""
) -> Reply:
    """Send one request with the target written exactly as given, which httpx would rewrite."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    lines = [f"{method} {target} HTTP/1.1", f"Host: 127.0.0.1:{port}", "Connection: close"]
    lines += [f"{name}: {value}" for name, value in headers]
    if body:
        lines.append(f"Content-Length: {len(body)}")
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body)
    await writer.drain()
    data = await asyncio.wait_for(reader.read(), 10)
    writer.close()
    await writer.wait_closed()
    head, _, rest = data.partition(b"\r\n\r\n")
    first, *header_lines = head.decode("latin-1").split("\r\n")
    parsed = [
        (k.strip().lower(), v.strip()) for k, _, v in (line.partition(":") for line in header_lines)
    ]
    if ("transfer-encoding", "chunked") in parsed:
        rest = _unchunk(rest)
    return Reply(int(first.split()[1]), parsed, rest)


def _unchunk(data: bytes) -> bytes:
    out = b""
    while data:
        size, _, data = data.partition(b"\r\n")
        count = int(size, 16)
        if count == 0:
            break
        out += data[:count]
        data = data[count + 2 :]
    return out
