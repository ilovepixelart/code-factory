"""Delivering a message to a real HTTP server on this machine."""

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

import pytest

from code_factory.push.adapters import NO_ANSWER, HttpDelivery
from code_factory.push.models import Message, Target

MESSAGE = Message(
    digest="d", kind="permission", repository="sample", ticket="CF-1",
    text="CF-1: an agent asks permission", anchor="perm-a",
)  # fmt: skip
LINK, REPLY = "http://localhost:4000/inbox#perm-a", "http://localhost:4000/reply/abc"


@dataclass
class Receiver:
    """An HTTP server answering `status` and keeping each request's head and body."""

    status: int = 200
    seen: list[tuple[dict[str, str], bytes]] = field(default_factory=list)
    port: int = 0

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = (await reader.readuntil(b"\r\n\r\n")).decode().split("\r\n")
        headers = {k.lower(): v for k, _, v in (line.partition(": ") for line in head[1:] if line)}
        body = await reader.readexactly(int(headers.get("content-length", "0")))
        self.seen.append((headers, body))
        writer.write(f"HTTP/1.1 {self.status} X\r\ncontent-length: 0\r\n\r\n".encode())
        await writer.drain()
        writer.close()


@pytest.fixture
async def receiver() -> AsyncGenerator[Receiver]:
    found = Receiver()
    server = await asyncio.start_server(found.handle, "127.0.0.1", 0)
    found.port = server.sockets[0].getsockname()[1]
    async with server:
        yield found


async def test_ntfy_gets_the_sentence_with_its_title_click_and_reply_action(
    receiver: Receiver,
) -> None:
    target = Target(format="ntfy", url=f"http://127.0.0.1:{receiver.port}/topic")

    problem = await HttpDelivery().deliver(target, MESSAGE, LINK, REPLY)

    [(headers, body)] = receiver.seen
    assert problem is None
    assert body.decode() == "CF-1: an agent asks permission"
    assert (headers["title"], headers["click"], headers["actions"]) == (
        "code-factory", LINK, f"view, Reply, {REPLY}",
    )  # fmt: skip


async def test_a_webhook_gets_json_naming_the_item_and_never_more(receiver: Receiver) -> None:
    target = Target(format="webhook", url=f"http://127.0.0.1:{receiver.port}/hook")

    await HttpDelivery().deliver(target, MESSAGE, LINK, "")

    [(_, body)] = receiver.seen
    assert json.loads(body) == {
        "kind": "permission", "repository": "sample", "ticket": "CF-1",
        "text": "CF-1: an agent asks permission", "link": LINK,
    }  # fmt: skip


async def test_a_refusing_server_is_its_status_and_no_server_no_answer(
    receiver: Receiver, unused_tcp_port: int
) -> None:
    receiver.status = 500
    refused = await HttpDelivery().deliver(
        Target(format="ntfy", url=f"http://127.0.0.1:{receiver.port}/t"), MESSAGE, LINK, ""
    )
    absent = await HttpDelivery().deliver(
        Target(format="ntfy", url=f"http://127.0.0.1:{unused_tcp_port}/t"), MESSAGE, LINK, ""
    )
    assert (refused, absent) == ("HTTP 500", NO_ANSWER)
