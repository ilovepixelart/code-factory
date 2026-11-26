"""One request through the listener and what the broker answers itself."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

NO_STORE = ("cache-control", "no-store")
NOT_LIVE_SENTENCE = "not a live run token"
REFUSED_SENTENCE = "the key broker does not send this request"
NO_CONNECTION_SENTENCE = "this run has no model connection"
TOO_LARGE_SENTENCE = "the request body is too large"
COULD_NOT_SENTENCE = "the key broker could not send this request"
STOPPED_SENTENCE = "the key broker is stopped"
UNREADABLE_SENTENCE = "the provider answered with an error the key broker cannot show"
NOT_JSON_SENTENCE = "the export is not JSON"
NOT_FOUND_SENTENCE = "no such path"
NOT_ALLOWED_SENTENCE = "this path takes another method"


class BodyTooLargeError(Exception):
    """The request body went past the limit while it was being read."""


class ClientGoneError(Exception):
    """The client closed the connection before the request was complete."""


async def _no_chunks() -> AsyncIterator[bytes]:
    return
    yield b""  # pragma: no cover  # makes this an async generator


@dataclass
class ProxyRequest:
    """A request to forward: the target and headers as received, the body a stream or `None`."""

    method: str
    raw_target: str
    headers: list[tuple[str, str]]
    body: AsyncIterator[bytes] | None = None
    content_length: int | None = None


@dataclass
class ProxyAnswer:
    """What goes back to the run: a status, headers and a body streamed chunk by chunk.

    `ended` is set when the run's token ends, so the relay stops; `close` releases the upstream.
    """

    status: int
    headers: list[tuple[str, str]]
    body: AsyncIterator[bytes] = field(default_factory=_no_chunks)
    ended: asyncio.Event | None = None
    close: Callable[[], Awaitable[None]] | None = field(default=None, repr=False)


async def once(data: bytes) -> AsyncIterator[bytes]:
    """A body of one chunk."""
    yield data


def json_answer(
    status: int, payload: dict[str, str], extra: list[tuple[str, str]] | None = None
) -> ProxyAnswer:
    """An answer the broker makes itself: a small JSON object and nothing the provider said."""
    body = json.dumps(payload).encode()
    headers = [
        ("content-type", "application/json"),
        ("content-length", str(len(body))),
        NO_STORE,
        *(extra or []),
    ]
    return ProxyAnswer(status, headers, once(body))


def fixed(status: int, sentence: str, extra: list[tuple[str, str]] | None = None) -> ProxyAnswer:
    """An answer with a constant `{"error": sentence}` body."""
    return json_answer(status, {"error": sentence}, extra)
