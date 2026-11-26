"""Sending one run request on to the provider with the real credential, and relaying the answer.

Nothing here puts a key, a token or anything the provider said into a log or an error: the
answers the broker makes itself are the constant sentences of `exchange`.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from pydantic import SecretStr

from code_factory.broker.adapters.provider import ProviderClient, Upstream, UpstreamError
from code_factory.broker.models import (
    CODEX_LOGIN,
    BrokerConnection,
    Refusal,
    TokenGrant,
)
from code_factory.broker.ports import ConnectionSource, RunControl
from code_factory.broker.rules.headers import credential_header, outbound_headers, response_headers
from code_factory.broker.rules.scrub import ERROR_BODY_LIMIT, error_body
from code_factory.broker.rules.targets import request_target
from code_factory.broker.service.exchange import (
    COULD_NOT_SENTENCE,
    NO_CONNECTION_SENTENCE,
    NO_STORE,
    NOT_LIVE_SENTENCE,
    REFUSED_SENTENCE,
    TOO_LARGE_SENTENCE,
    UNREADABLE_SENTENCE,
    BodyTooLargeError,
    ProxyAnswer,
    ProxyRequest,
    fixed,
    once,
)
from code_factory.broker.service.runkeys import NoRunKeyError, RunKeys
from code_factory.platform.errors import BadRequestError, NotFoundError, UnavailableError

logger = logging.getLogger(__name__)

CODEX_EXPIRED = "the codex login has expired: run `codex` once on this machine to renew it"
HALT_S = 5.0
_UNAUTHORIZED = 401
_ERROR_FROM = 400


@dataclass(frozen=True)
class Credential:
    """What a request goes out with: the header, headers of its own, and every secret in play."""

    header: tuple[str, str]
    extra: tuple[tuple[str, str], ...]
    secrets: tuple[str, ...]


async def _counted(body: AsyncIterator[bytes], limit: int) -> AsyncIterator[bytes]:
    """The body, failing once more than `limit` bytes have passed."""
    seen = 0
    async for chunk in body:
        seen += len(chunk)
        if seen > limit:
            raise BodyTooLargeError
        yield chunk


async def _read_capped(upstream: Upstream) -> bytes:
    data = b""
    async for chunk in upstream.chunks():
        data += chunk
        if len(data) > ERROR_BODY_LIMIT:
            break
    return data


class Forwarder:
    """The proxy handler: from a live token's grant and a request to the answer."""

    def __init__(  # noqa: PLR0913, PLR0917  # the collaborators of one handler
        self,
        connections: ConnectionSource,
        keys: RunKeys,
        provider: ProviderClient,
        control: Callable[[], RunControl | None],
        max_body: int,
        streams: dict[str, set[asyncio.Event]],
    ) -> None:
        self._connections = connections
        self._keys = keys
        self._provider = provider
        self._control = control
        self._max_body = max_body
        self._streams = streams
        self._tasks: set[asyncio.Task[None]] = set()

    async def forward(self, grant: TokenGrant, request: ProxyRequest) -> ProxyAnswer:
        """Send the request on for the run, or say with a fixed sentence why not."""
        connection = await self._connection(grant)
        if isinstance(connection, ProxyAnswer):
            return connection
        path = self._path(connection, request)
        if isinstance(path, ProxyAnswer):
            return path
        try:
            credential = await self._credential(grant, connection)
        except NoRunKeyError, UnavailableError, BadRequestError:
            return fixed(502, COULD_NOT_SENTENCE)
        return await self._send(grant, connection, path, request, credential)

    async def _connection(self, grant: TokenGrant) -> BrokerConnection | ProxyAnswer:
        """The run's connection when it exists and keeps its rules, else the answer."""
        if grant.connection is None:
            return fixed(403, NO_CONNECTION_SENTENCE)
        try:
            connection = await self._connections.get_connection(grant.connection)
        except NotFoundError:
            return fixed(401, NOT_LIVE_SENTENCE)  # the connection is gone: the run is ending
        try:
            self._connections.check_rules(connection)
        except BadRequestError:
            return fixed(502, COULD_NOT_SENTENCE)
        return connection

    def _path(self, connection: BrokerConnection, request: ProxyRequest) -> str | ProxyAnswer:
        """The path to send to, else the answer for a refused target or a body too large."""
        target = request_target(connection.kind, request.method, request.raw_target)
        if isinstance(target, Refusal):
            if connection.kind == CODEX_LOGIN:
                path = request.raw_target.partition("?")[0]
                logger.warning("codex request refused: %r %r", request.method, path)
            return fixed(403, REFUSED_SENTENCE)
        if request.content_length is not None and request.content_length > self._max_body:
            return fixed(413, TOO_LARGE_SENTENCE)
        return target.path

    async def _credential(self, grant: TokenGrant, connection: BrokerConnection) -> Credential:
        """The credential for this request alone: the login, the run key, or the connection key."""
        if connection.kind == CODEX_LOGIN:
            login = await self._connections.read_codex_login()
            token = login.access_token.get_secret_value()
            account = ("chatgpt-account-id", login.account_id)
            return Credential(credential_header(connection.kind, token), (account,), (token,))
        key: SecretStr | None
        if grant.cap_usd is not None:
            key = await self._keys.key_for(grant, connection)
        else:
            key = (
                await self._connections.read_key(connection.key_name)
                if connection.key_name
                else None
            )
        if key is None:
            raise NoRunKeyError
        secret = key.get_secret_value()
        return Credential(credential_header(connection.kind, secret), (), (secret,))

    async def _send(  # one request's parts
        self,
        grant: TokenGrant,
        connection: BrokerConnection,
        path: str,
        request: ProxyRequest,
        credential: Credential,
    ) -> ProxyAnswer:
        headers = outbound_headers(request.headers, credential.header, credential.extra)
        body = None if request.body is None else _counted(request.body, self._max_body)
        try:
            upstream = await self._provider.stream_request(
                request.method, connection.base_url, path, headers, body
            )
        except UpstreamError:
            return fixed(502, COULD_NOT_SENTENCE)
        except BodyTooLargeError:
            return fixed(413, TOO_LARGE_SENTENCE)
        if connection.kind == CODEX_LOGIN and upstream.status == _UNAUTHORIZED:
            await self._halt(grant.run_id)
        if upstream.status >= _ERROR_FROM:
            return await self._error_answer(upstream, credential.secrets)
        return self._streamed(grant.run_id, upstream, credential.secrets)

    async def _error_answer(self, upstream: Upstream, secrets: tuple[str, ...]) -> ProxyAnswer:
        """An error of the provider, buffered, decoded, cut and scrubbed."""
        try:
            data = await _read_capped(upstream)
        except UpstreamError:
            return fixed(502, COULD_NOT_SENTENCE)
        finally:
            await upstream.aclose()
        encoding = next((v for k, v in upstream.headers if k.lower() == "content-encoding"), None)
        shown = error_body(encoding, data, secrets)
        if shown is None:
            return fixed(upstream.status, UNREADABLE_SENTENCE)
        kept = [
            (name, value)
            for name, value in response_headers(upstream.headers, secrets)
            if name.lower() not in {"content-length", "content-encoding"}
        ]
        kept = [*kept, ("content-length", str(len(shown))), NO_STORE]
        return ProxyAnswer(upstream.status, kept, once(shown))

    def _streamed(self, run_id: str, upstream: Upstream, secrets: tuple[str, ...]) -> ProxyAnswer:
        ended = asyncio.Event()
        self._streams.setdefault(run_id, set()).add(ended)

        async def close() -> None:
            self._streams.get(run_id, set()).discard(ended)
            await upstream.aclose()

        return ProxyAnswer(
            upstream.status,
            response_headers(upstream.headers, secrets),
            upstream.chunks(),
            ended,
            close,
        )

    async def _halt(self, run_id: str) -> None:
        """Tell the run control the login expired, in a task a gone client cannot cancel."""
        control = self._control()
        if control is None:
            return
        task = asyncio.create_task(self._halt_run(control.halt_run, run_id), name="broker-halt")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        await asyncio.shield(task)

    @staticmethod
    async def _halt_run(halt: Callable[[str, str], Awaitable[None]], run_id: str) -> None:
        try:
            async with asyncio.timeout(HALT_S):
                await halt(run_id, CODEX_EXPIRED)
        except Exception:  # noqa: BLE001  # the 401 still goes to the run; the halt is best effort
            logger.warning("the run could not be halted after the codex login expired")
