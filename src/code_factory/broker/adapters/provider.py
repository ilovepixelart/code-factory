"""The client that sends requests to the provider, and the calls that make and delete run keys.

Every external await sits under `asyncio.timeout`. A secret is unwrapped only here and only into
a header, and nothing the provider answers is put in an error or a reason.
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator, Sequence

import httpx
from pydantic import SecretStr

from code_factory.broker.models import (
    WHY_ID,
    WHY_REFUSED,
    WHY_SILENT,
    DeleteResult,
    KeyCreated,
)
from code_factory.broker.rules.keys import run_key_made

_KEY_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_ANSWER_CAP = 64 * 1024
_NOT_FOUND = 404
_OK = 2
_CALLS_AT_ONCE = 4


class UpstreamError(Exception):
    """The provider could not be reached or stopped answering; the text names no address."""


class Upstream:
    """An open response, never read whole: the caller closes it."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.status = response.status_code
        self.headers = list(response.headers.multi_items())

    async def chunks(self) -> AsyncIterator[bytes]:
        """The body as it arrives, undecoded; `UpstreamError` when the provider stops sending."""
        try:
            async for chunk in self._response.aiter_raw():
                yield chunk
        except httpx.HTTPError, OSError:
            raise UpstreamError("the provider stopped answering") from None

    async def aclose(self) -> None:
        """Release the connection."""
        await self._response.aclose()


class ProviderClient:
    """One client for every request: no cookies kept, no redirects, no environment, no defaults."""

    def __init__(  # the five limits of one client
        self,
        *,
        read_s: float,
        connect_s: float = 10.0,
        write_s: float = 60.0,
        pool_s: float = 10.0,
        max_connections: int = 64,
    ) -> None:
        self._budget = connect_s + write_s + read_s + pool_s
        self._client = httpx.AsyncClient(
            trust_env=False,
            follow_redirects=False,
            http2=False,
            verify=True,
            timeout=httpx.Timeout(connect=connect_s, write=write_s, read=read_s, pool=pool_s),
            limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=16),
        )

    async def stream_request(  # the parts of one request
        self,
        method: str,
        base_url: str,
        target: str,
        headers: Sequence[tuple[str, str]],
        body: AsyncIterator[bytes] | None = None,
    ) -> Upstream:
        """Send the request and return its response with the body unread.

        The path is the base's path and the target concatenated as strings, never resolved.
        """
        base = httpx.URL(base_url)
        url = base.copy_with(raw_path=base.raw_path.rstrip(b"/") + target.encode("ascii"))
        request = httpx.Request(method, url, headers=list(headers), content=body)
        try:
            async with asyncio.timeout(self._budget):
                response = await self._client.send(request, stream=True, follow_redirects=False)
        except httpx.HTTPError, OSError, TimeoutError:
            raise UpstreamError("the provider could not be reached") from None
        return Upstream(response)

    async def aclose(self) -> None:
        """Close every connection."""
        await self._client.aclose()


class KeyApi:
    """Makes and deletes a run key with the connection's management key."""

    def __init__(self, client: ProviderClient, *, call_s: float) -> None:
        self._client = client
        self._call_s = call_s
        self._at_once = asyncio.Semaphore(_CALLS_AT_ONCE)

    async def _call(
        self, method: str, base: str, path: str, management: SecretStr, body: bytes | None
    ) -> tuple[int, bytes]:
        """One call within the call limit; the status and the first 64 KiB of the answer."""
        headers = [("authorization", f"Bearer {management.get_secret_value()}")]
        if body is not None:
            headers += [("content-type", "application/json"), ("content-length", str(len(body)))]

        async def one() -> AsyncIterator[bytes]:
            yield body or b""

        async with self._at_once, asyncio.timeout(self._call_s):
            upstream = await self._client.stream_request(
                method, base, path, headers, one() if body is not None else None
            )
            try:
                data = b""
                async for chunk in upstream.chunks():
                    data += chunk
                    if len(data) >= _ANSWER_CAP:
                        break
                return upstream.status, data[:_ANSWER_CAP]
            finally:
                await upstream.aclose()

    async def create(self, base: str, management: SecretStr, body: dict[str, object]) -> KeyCreated:
        """Ask the provider for a key; `answered` is false when it said nothing in time."""
        try:
            status, data = await self._call(
                "POST", base, "/v1/keys", management, json.dumps(body).encode()
            )
        except UpstreamError, TimeoutError:
            return KeyCreated(made=None, answered=False)
        try:
            parsed: object = json.loads(data)
        except ValueError:
            parsed = None
        return KeyCreated(made=run_key_made(status, parsed), answered=True)

    async def delete(self, base: str, management: SecretStr, key_id: str) -> DeleteResult:
        """Delete a key at the provider; a 2xx and a 404 both mean it is gone."""
        if _KEY_ID.fullmatch(key_id) is None:
            return DeleteResult(ok=False, why=WHY_ID)
        try:
            status, _ = await self._call("DELETE", base, f"/v1/keys/{key_id}", management, None)
        except UpstreamError, TimeoutError:
            return DeleteResult(ok=False, why=WHY_SILENT)
        if status // 100 == _OK or status == _NOT_FOUND:
            return DeleteResult(ok=True)
        return DeleteResult(ok=False, why=WHY_REFUSED)
