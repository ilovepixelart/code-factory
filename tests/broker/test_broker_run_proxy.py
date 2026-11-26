"""The run proxy: a CONNECT filter on loopback that lets a container reach only its model host."""

import asyncio
from collections.abc import AsyncGenerator

import pytest

from code_factory.broker.adapters.proxy import RunProxyServer


class Echo:
    """A local TCP server that echoes what it receives and counts its connections."""

    def __init__(self) -> None:
        self.connections = 0
        self.server: asyncio.Server | None = None
        self.port = 0

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        try:
            while data := await reader.read(1024):
                writer.write(data)
                await writer.drain()
        finally:
            writer.close()


@pytest.fixture
async def echo() -> AsyncGenerator[Echo]:
    made = Echo()
    made.server = await asyncio.start_server(made.handle, "127.0.0.1", 0)
    made.port = made.server.sockets[0].getsockname()[1]
    yield made
    made.server.close()
    await made.server.wait_closed()


async def request(
    proxy: RunProxyServer, head: bytes
) -> tuple[bytes, asyncio.StreamReader, asyncio.StreamWriter]:
    host, port = proxy.address.rsplit(":", 1)
    reader, writer = await asyncio.open_connection(host, int(port))
    writer.write(head)
    await writer.drain()
    answer = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
    return answer, reader, writer


def connect(target: str) -> bytes:
    return f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode()


@pytest.fixture
async def proxy(echo: Echo) -> AsyncGenerator[RunProxyServer]:
    made = RunProxyServer([f"127.0.0.1:{echo.port}"], head_timeout_s=0.3, idle_s=0.4, max_tunnels=2)
    await made.start()
    yield made
    await made.stop()


async def test_connect_to_the_allowed_host_answers_200_and_relays_both_ways(
    proxy: RunProxyServer, echo: Echo
) -> None:
    answer, reader, writer = await request(proxy, connect(f"127.0.0.1:{echo.port}"))
    assert answer.startswith(b"HTTP/1.1 200")
    writer.write(b"ping")
    await writer.drain()
    assert await asyncio.wait_for(reader.readexactly(4), 3) == b"ping"
    writer.close()


async def test_connect_elsewhere_is_403_with_a_reason_and_is_recorded_and_nothing_connects(
    proxy: RunProxyServer, echo: Echo
) -> None:
    answer, _, writer = await request(proxy, connect("evil.example:443"))
    assert answer.startswith(b"HTTP/1.1 403")
    assert echo.connections == 0
    assert len(proxy.refusals) == 1
    assert "evil.example:443" in proxy.refusals[0]
    writer.close()


async def test_a_plain_get_is_405(proxy: RunProxyServer) -> None:
    answer, _, writer = await request(proxy, b"GET http://x/ HTTP/1.1\r\nHost: x\r\n\r\n")
    assert answer.startswith(b"HTTP/1.1 405")
    writer.close()


async def _closed_without_relay(reader: asyncio.StreamReader) -> bool:
    return await asyncio.wait_for(reader.read(100), 3) == b""


async def test_a_head_past_8_kib_is_closed_with_no_relay(proxy: RunProxyServer, echo: Echo) -> None:
    host, port = proxy.address.rsplit(":", 1)
    reader, writer = await asyncio.open_connection(host, int(port))
    writer.write(b"CONNECT " + b"a" * 9000)
    await writer.drain()
    assert await _closed_without_relay(reader)
    assert echo.connections == 0
    writer.close()


async def test_a_head_never_finished_is_closed_after_the_head_limit(proxy: RunProxyServer) -> None:
    host, port = proxy.address.rsplit(":", 1)
    reader, writer = await asyncio.open_connection(host, int(port))
    writer.write(b"CONNECT 127.0.0.1:1 HTTP/1.1\r\n")
    await writer.drain()
    assert await _closed_without_relay(reader)
    writer.close()


@pytest.mark.parametrize(
    "target",
    ["a@127.0.0.1:1", "[::1]:1", "127.0.0.1:0", "127.0.0.1:00443", "127.0.0.1:1 "],
)
async def test_hostile_connect_targets_are_refused(
    proxy: RunProxyServer, echo: Echo, target: str
) -> None:
    answer, _, w = await request(proxy, f"CONNECT {target} HTTP/1.1\r\n\r\n".encode())
    assert answer.startswith(b"HTTP/1.1 403")
    assert echo.connections == 0
    w.close()


async def test_an_uppercase_host_is_allowed_after_lowering(echo: Echo) -> None:
    proxy = RunProxyServer(["localhost:" + str(echo.port)], head_timeout_s=1, idle_s=5)
    await proxy.start()
    try:
        answer, _, writer = await request(proxy, connect(f"LOCALHOST:{echo.port}"))
        assert answer.startswith(b"HTTP/1.1 200")
        writer.close()
    finally:
        await proxy.stop()


async def test_the_tunnel_after_the_limit_is_refused(proxy: RunProxyServer, echo: Echo) -> None:
    held = []
    for _ in range(2):
        answer, _, writer = await request(proxy, connect(f"127.0.0.1:{echo.port}"))
        assert answer.startswith(b"HTTP/1.1 200")
        held.append(writer)
    answer, _, writer = await request(proxy, connect(f"127.0.0.1:{echo.port}"))
    assert answer.startswith(b"HTTP/1.1 503")
    assert echo.connections == 2
    for w in (*held, writer):
        w.close()


async def test_an_idle_tunnel_closes_after_the_idle_limit(
    proxy: RunProxyServer, echo: Echo
) -> None:
    answer, reader, writer = await request(proxy, connect(f"127.0.0.1:{echo.port}"))
    assert answer.startswith(b"HTTP/1.1 200")
    assert await asyncio.wait_for(reader.read(10), 3) == b""
    writer.close()


async def test_stopping_closes_the_listener_and_every_tunnel(echo: Echo) -> None:
    proxy = RunProxyServer([f"127.0.0.1:{echo.port}"], idle_s=30)
    await proxy.start()
    answer, reader, writer = await request(proxy, connect(f"127.0.0.1:{echo.port}"))
    assert answer.startswith(b"HTTP/1.1 200")
    await proxy.stop()
    assert await asyncio.wait_for(reader.read(10), 3) == b""
    host, port = proxy.address.rsplit(":", 1)
    with pytest.raises(OSError, match=r"refused|Connect"):
        await asyncio.open_connection(host, int(port))
    writer.close()


async def test_a_target_that_does_not_answer_is_502() -> None:
    proxy = RunProxyServer(["127.0.0.1:1"], head_timeout_s=1, idle_s=5)
    await proxy.start()
    try:
        answer, _, writer = await request(proxy, connect("127.0.0.1:1"))
        assert answer.startswith(b"HTTP/1.1 502")
        writer.close()
    finally:
        await proxy.stop()


async def test_only_one_hundred_refusals_are_kept(echo: Echo) -> None:
    proxy = RunProxyServer([f"127.0.0.1:{echo.port}"], head_timeout_s=1)
    await proxy.start()
    try:
        for index in range(105):
            _, _, writer = await request(proxy, connect(f"evil{index}.example:443"))
            writer.close()
        assert len(proxy.refusals) == 100
        assert "evil104.example:443" in proxy.refusals[-1]
    finally:
        await proxy.stop()
