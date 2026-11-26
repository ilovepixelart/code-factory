"""The listener's ASGI app: pure ASGI, no routing, no middleware of the main app.

`POST /telemetry/v1/logs` goes to the telemetry handler, any other path under `/telemetry` is 404,
and everything else is the proxy. Bodies stream both ways; a client that disconnects ends the
upstream read.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any

from code_factory.broker.models import TOKEN_HEADER, TokenRefusedError
from code_factory.broker.service.exchange import (
    NOT_ALLOWED_SENTENCE,
    NOT_FOUND_SENTENCE,
    NOT_JSON_SENTENCE,
    NOT_LIVE_SENTENCE,
    TOO_LARGE_SENTENCE,
    BodyTooLargeError,
    ClientGoneError,
    ProxyAnswer,
    ProxyRequest,
    fixed,
    json_answer,
)
from code_factory.platform.errors import BadRequestError

if TYPE_CHECKING:
    from code_factory.broker.service import BrokerService

type Scope = dict[str, Any]
type Message = dict[str, Any]

TELEMETRY = b"/telemetry"
TELEMETRY_LOGS = b"/telemetry/v1/logs"
TELEMETRY_LIMIT = 1024 * 1024


class _Receiver:
    """The request body as a stream, and the disconnect that follows it.

    Both read `receive()`, so the disconnect watcher waits until the body is read.
    """

    def __init__(self, receive: Any) -> None:  # noqa: ANN401  # the ASGI receive callable
        self._receive = receive
        self._body_done = asyncio.Event()

    def mark_done(self) -> None:
        """No body will be read: a disconnect may be watched for at once."""
        self._body_done.set()

    async def body(self) -> AsyncIterator[bytes]:
        """The body chunks; `ClientGoneError` when the client disconnects first."""
        try:
            while True:
                message: Message = await self._receive()
                if message["type"] == "http.disconnect":
                    raise ClientGoneError
                if chunk := bytes(message.get("body", b"")):
                    yield chunk
                if not message.get("more_body", False):
                    return
        finally:
            self._body_done.set()

    async def disconnected(self) -> None:
        """Return when the client has gone."""
        await self._body_done.wait()
        while (await self._receive())["type"] != "http.disconnect":
            pass


def _headers(scope: Scope) -> list[tuple[str, str]]:
    return [(k.decode("latin-1"), v.decode("latin-1")) for k, v in scope["headers"]]


def _target(scope: Scope) -> str:
    raw = bytes(scope["raw_path"])
    query = bytes(scope["query_string"])
    return (raw + (b"?" + query if query else b"")).decode("latin-1")


def _length(headers: list[tuple[str, str]]) -> int | None:
    value = next((v for k, v in headers if k.lower() == "content-length"), None)
    return int(value) if value is not None and value.isascii() and value.isdigit() else None


def _has_body(headers: list[tuple[str, str]]) -> bool:
    return any(k.lower() == "transfer-encoding" for k, _ in headers) or (_length(headers) or 0) > 0


class BrokerApp:
    """The ASGI application of the run listener."""

    def __init__(self, service: BrokerService) -> None:
        self._service = service

    async def __call__(self, scope: Scope, receive: Any, send: Any) -> None:  # noqa: ANN401
        """Serve one HTTP request; anything else is ignored."""
        if scope["type"] != "http":
            return
        receiver = _Receiver(receive)
        raw = bytes(scope["raw_path"])
        try:
            if raw.startswith(TELEMETRY):
                answer = await self._telemetry(scope, receiver)
            else:
                answer = await self._proxy(scope, receiver)
        except ClientGoneError:
            return
        await self._relay(answer, receiver, send)

    async def _proxy(self, scope: Scope, receiver: _Receiver) -> ProxyAnswer:
        headers = _headers(scope)
        method = str(scope["method"])
        if _has_body(headers):
            body: AsyncIterator[bytes] | None = receiver.body()
        else:
            body = None
            receiver.mark_done()
        request = ProxyRequest(method, _target(scope), headers, body, _length(headers))
        return await self._service.proxy(request)

    async def _telemetry(self, scope: Scope, receiver: _Receiver) -> ProxyAnswer:
        receiver.mark_done()
        if bytes(scope["raw_path"]) != TELEMETRY_LOGS:
            return fixed(404, NOT_FOUND_SENTENCE)
        if scope["method"] != "POST":
            return fixed(405, NOT_ALLOWED_SENTENCE, [("allow", "POST")])
        headers = _headers(scope)
        token = next((v for k, v in headers if k.lower() == TOKEN_HEADER), "")
        if await self._service.verify(token) is None:
            return fixed(401, NOT_LIVE_SENTENCE)
        return await self._record(token, receiver, _length(headers))

    async def _record(self, token: str, receiver: _Receiver, length: int | None) -> ProxyAnswer:
        """Read the export, at most 1 MiB counted as it arrives, and hand it to the sessions."""
        if length is not None and length > TELEMETRY_LIMIT:
            return fixed(413, TOO_LARGE_SENTENCE)
        try:
            data = await _read(receiver, TELEMETRY_LIMIT)
            await self._service.receive_telemetry(token, data)
        except BodyTooLargeError:
            return fixed(413, TOO_LARGE_SENTENCE)
        except TokenRefusedError:
            return fixed(401, NOT_LIVE_SENTENCE)
        except BadRequestError:
            return fixed(400, NOT_JSON_SENTENCE)
        return json_answer(200, {})

    @staticmethod
    async def _relay(answer: ProxyAnswer, receiver: _Receiver, send: Any) -> None:  # noqa: ANN401
        """Send the answer chunk by chunk, stopping when the run ends or the client goes."""
        watchers = [asyncio.ensure_future(receiver.disconnected())]
        if answer.ended is not None:
            watchers.append(asyncio.ensure_future(answer.ended.wait()))
        chunks = answer.body.__aiter__()
        try:
            await send(
                {
                    "type": "http.response.start",
                    "status": answer.status,
                    "headers": [
                        (k.encode("latin-1"), v.encode("latin-1")) for k, v in answer.headers
                    ],
                }
            )
            while (chunk := await _next(chunks, watchers)) is not None:
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            for watcher in watchers:
                watcher.cancel()
            await asyncio.gather(*watchers, return_exceptions=True)
            if answer.close is not None:
                await answer.close()


async def _read(receiver: _Receiver, limit: int) -> bytes:
    data = b""
    async for chunk in receiver.body():
        data += chunk
        if len(data) > limit:
            raise BodyTooLargeError
    return data


async def _next(
    chunks: AsyncIterator[bytes], watchers: Sequence[asyncio.Future[Any]]
) -> bytes | None:
    """The next chunk, or `None` when the body is over or a watcher fired first."""
    pending = asyncio.ensure_future(anext(chunks))
    done, _ = await asyncio.wait({pending, *watchers}, return_when=asyncio.FIRST_COMPLETED)
    if pending not in done:
        pending.cancel()
        with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
            await pending
        return None
    try:
        return pending.result()
    except StopAsyncIteration:
        return None
