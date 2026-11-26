"""A fake model server on a free loopback port: records each request, answers with a canned
response or holds the request open."""

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

Answer = Callable[[str], str | None]


def respond(status: str, body: str, *, headers: str = "") -> str:
    """An HTTP/1.1 response text with `body`."""
    return (
        f"HTTP/1.1 {status}\r\ncontent-type: application/json\r\ncontent-length: {len(body)}\r\n"
        f"{headers}connection: close\r\n\r\n{body}"
    )


@dataclass
class Stub:
    """The address a stub listens on and the requests it saw as (head, body)."""

    address: str
    requests: list[tuple[str, str]] = field(default_factory=list)

    def heads(self) -> list[str]:
        return [head for head, _ in self.requests]


@asynccontextmanager
async def serve(answer: Answer) -> AsyncGenerator[Stub]:
    """Serve `answer(head)` (a full response, or None to hold the request open)."""
    stub = Stub("")
    held: list[asyncio.StreamWriter] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = (await reader.readuntil(b"\r\n\r\n")).decode()
        length = 0
        for line in head.splitlines():
            name, _, value = line.partition(":")
            if name.lower() == "content-length":
                length = int(value)
        body = (await reader.readexactly(length)).decode() if length else ""
        stub.requests.append((head, body))
        response = answer(head)
        if response is None:
            held.append(writer)
            return
        writer.write(response.encode())
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    stub.address = f"http://127.0.0.1:{port}"
    try:
        yield stub
    finally:
        server.close()
        for writer in held:
            writer.close()
        await server.wait_closed()


def closed_address() -> str:
    """A loopback address nothing listens on: a port bound, then let go."""
    import socket  # noqa: PLC0415

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{probe.getsockname()[1]}"
