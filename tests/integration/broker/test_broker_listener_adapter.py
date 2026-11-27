"""The run listener: loopback only, released on stop, and no header or log of its own."""

import asyncio
import contextlib
import gc
import logging
import signal
import socket

import httpx
import pytest

from broker_support import Receive, Scope, Send, reply
from code_factory.broker.adapters.listener import RunListener
from code_factory.platform.errors import UnavailableError


async def hello(scope: Scope, receive: Receive, send: Send) -> None:  # noqa: ARG001
    if scope["type"] == "http":
        await reply(send, 200, b"hi")


async def test_it_answers_on_a_loopback_port_and_releases_it_on_stop() -> None:
    listener = RunListener(hello, shutdown_timeout_s=2)
    port = await listener.start()
    async with httpx.AsyncClient() as client:
        answer = await client.get(f"http://127.0.0.1:{port}/x")
    assert (answer.status_code, answer.content) == (200, b"hi")
    await listener.stop()
    with pytest.raises(OSError, match=r"refused|Connect"):
        await asyncio.open_connection("127.0.0.1", port)
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", port))  # the port is free again
    finally:
        probe.close()


async def test_it_is_bound_to_loopback_only_never_to_the_machines_other_address() -> None:
    listener = RunListener(hello, shutdown_timeout_s=2)
    port = await listener.start()
    try:
        assert listener.address == ("127.0.0.1", port)
        other = _other_address()
        if other is not None:
            with pytest.raises(OSError, match=r"refused|Connect"):
                await asyncio.open_connection(other, port)
    finally:
        await listener.stop()


def _other_address() -> str | None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # no packet is sent: this only picks the outgoing address
        found = str(probe.getsockname()[0])
    except OSError:
        return None
    finally:
        probe.close()
    return None if found.startswith("127.") else found


async def test_it_sends_no_server_header_and_logs_no_access_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    listener = RunListener(hello, shutdown_timeout_s=2)
    port = await listener.start()
    try:
        with caplog.at_level(logging.DEBUG):
            async with httpx.AsyncClient() as client:
                answer = await client.get(f"http://127.0.0.1:{port}/v1/secret-path?q=secret-query")
    finally:
        await listener.stop()
    assert "server" not in answer.headers
    ours = " ".join(r.getMessage() for r in caplog.records if r.name.startswith("uvicorn"))
    assert "secret-path" not in ours
    assert "secret-query" not in ours


async def test_it_does_not_take_over_the_processs_signal_handlers() -> None:
    before = signal.getsignal(signal.SIGTERM)
    listener = RunListener(hello, shutdown_timeout_s=2)
    await listener.start()
    try:
        assert signal.getsignal(signal.SIGTERM) is before
    finally:
        await listener.stop()


async def test_stopping_a_listener_that_never_started_is_a_no_op() -> None:
    await RunListener(hello, shutdown_timeout_s=2).stop()


async def test_a_listener_that_cannot_start_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    listener = RunListener(hello, shutdown_timeout_s=0.2, start_timeout_s=0.01)

    async def never(*_: object, **__: object) -> None:
        await asyncio.sleep(10)

    monkeypatch.setattr("uvicorn.Server.serve", never)
    with pytest.raises(UnavailableError, match="listener"):
        await listener.start()


def _open_loopback_sockets() -> set[int]:
    found = set()
    for item in gc.get_objects():
        if (
            isinstance(item, socket.socket)
            and item.family == socket.AF_INET
            and item.fileno() != -1
        ):
            with contextlib.suppress(OSError):
                if item.getsockname()[0] == "127.0.0.1":
                    found.add(id(item))
    return found


async def test_a_start_cancelled_before_it_serves_releases_its_socket_and_server() -> None:
    before = _open_loopback_sockets()
    starting = asyncio.create_task(RunListener(hello, shutdown_timeout_s=2).start())
    await asyncio.sleep(0)  # the socket is bound and the server task created, not yet serving
    starting.cancel()

    with pytest.raises(asyncio.CancelledError):
        await starting
    serving = [t for t in asyncio.all_tasks() if t.get_name() == "broker-listener-serve"]
    assert [t for t in serving if not t.done()] == []
    assert _open_loopback_sockets() - before == set()
