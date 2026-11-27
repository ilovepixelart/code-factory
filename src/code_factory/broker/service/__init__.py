"""The broker service: the one public API of the module.

Other modules import this package and `code_factory.broker.models`, nothing else.
"""

import asyncio
import contextlib
import hmac
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import SecretStr

from code_factory.broker.adapters.listener import RunListener
from code_factory.broker.adapters.provider import KeyApi, ProviderClient
from code_factory.broker.adapters.proxy import RunProxyServer
from code_factory.broker.models import (
    CAP_LIMIT,
    CODEX_LOGIN,
    BrokerEndpoints,
    BrokerStatus,
    IssuedToken,
    SweepReport,
    TokenGrant,
    TokenInfo,
    TokenRefusedError,
    TokenRow,
)
from code_factory.broker.ports import ConnectionSource, RunControl, UsageSink
from code_factory.broker.repository import BrokerRepository
from code_factory.broker.rules.connect import allowed_hosts
from code_factory.broker.rules.tokens import digest, new_token, token_of, token_state, well_formed
from code_factory.broker.service.asgi import BrokerApp
from code_factory.broker.service.exchange import (
    NOT_JSON_SENTENCE,
    NOT_LIVE_SENTENCE,
    STOPPED_SENTENCE,
    ProxyAnswer,
    ProxyRequest,
    fixed,
)
from code_factory.broker.service.forwarding import Forwarder
from code_factory.broker.service.runkeys import RunKeys
from code_factory.broker.service.sweeping import Sweeper
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnavailableError,
)

__all__ = ["BrokerService"]

logger = logging.getLogger(__name__)

_MIB = 1024 * 1024


def utc_now() -> datetime:
    """The service's default clock."""
    return datetime.now(UTC)


class BrokerService:
    """Run tokens, the key broker, the telemetry receiver and the run proxy of this process."""

    def __init__(  # the collaborators of one service
        self,
        uow: UnitOfWork,
        settings: Settings,
        connections: ConnectionSource,
        usage: UsageSink,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow = uow
        self._settings = settings
        self._connections = connections
        self._usage = usage
        self._clock = clock
        self._control: RunControl | None = None
        self._provider = ProviderClient(
            read_s=settings.broker_read_timeout_s,
            connect_s=min(10.0, settings.broker_call_timeout_s),
        )
        self._key_api = KeyApi(self._provider, call_s=settings.broker_call_timeout_s)
        self._streams: dict[str, set[asyncio.Event]] = {}
        self._proxies: set[RunProxyServer] = set()
        self._port: int | None = None
        self._stopped = False
        self._released: asyncio.Event | None = None
        self._wake = asyncio.Event()
        self.stopping = asyncio.Event()
        self._keys = RunKeys(uow, self._key_api, connections, clock)
        self._forwarder = Forwarder(
            connections,
            self._keys,
            self._provider,
            lambda: self._control,
            settings.broker_max_body_mib * _MIB,
            self._streams,
        )
        self._sweeper = Sweeper(
            uow,
            self._key_api,
            connections,
            clock,
            lambda: self._control,
            settings.broker_call_timeout_s,
        )

    @property
    def stopped(self) -> bool:
        """Whether the service has been stopped: the listener answers 503."""
        return self._stopped

    def attach_run_control(self, control: RunControl) -> None:
        """Give the broker the runs module's liveness and halt; the runs module calls this."""
        self._control = control

    def endpoints(self, connection: str | None = None) -> BrokerEndpoints:
        """Where a run reaches the broker; `UnavailableError` when this process does not listen."""
        if self._port is None:
            where = (
                f"on connection {connection}" if connection is not None else "on a keyed connection"
            )
            msg = f"no key broker answers: start the board (code-factory serve) to run {where}"
            raise UnavailableError(msg)
        base = f"http://127.0.0.1:{self._port}"
        return BrokerEndpoints(proxy_url=base, telemetry_url=f"{base}/telemetry")

    async def issue_run_token(
        self,
        run_id: str,
        connection: str | None,
        cap_usd: Decimal | None,
        expires_at: datetime,
    ) -> IssuedToken:
        """A token for one run, shown only here; its digest is the only thing stored."""
        endpoints = self.endpoints(connection)
        await self._check_issue(connection, cap_usd)
        token = new_token()
        async with self._uow() as session:
            added = await BrokerRepository(session).add(
                digest(token), run_id, connection, cap_usd, self._clock(), expires_at
            )
        if not added:
            msg = f"run {run_id} already holds a broker token"
            raise ConflictError(msg)
        secret = SecretStr(token)
        environment: dict[str, SecretStr | str] = {}
        if connection is not None:
            environment = {
                "ANTHROPIC_BASE_URL": endpoints.proxy_url,
                "ANTHROPIC_AUTH_TOKEN": secret,
                "ANTHROPIC_API_KEY": "",
            }
        return IssuedToken(
            token=secret,
            proxy_url=endpoints.proxy_url,
            telemetry_url=endpoints.telemetry_url,
            environment=environment,
        )

    async def _check_issue(self, connection: str | None, cap_usd: Decimal | None) -> None:
        if cap_usd is not None and not 0 <= cap_usd < CAP_LIMIT:
            msg = "a run's cap is at least 0 and under 1000000 dollars"
            raise BadRequestError(msg)
        if connection is None:
            if cap_usd is not None:
                msg = "a cap needs a connection"
                raise BadRequestError(msg)
            return
        try:
            known = await self._connections.get_connection(connection)
        except NotFoundError:
            msg = f"no connection named {connection}"
            raise BadRequestError(msg) from None
        self._connections.check_rules(known)
        if cap_usd is not None and known.kind == CODEX_LOGIN:
            msg = "a codex login connection takes no cap"
            raise BadRequestError(msg)

    async def verify(self, token: str) -> TokenGrant | None:
        """What a live token stands for; `None` for any other. Reads one row, writes nothing."""
        if not well_formed(token):
            return None
        wanted = digest(token)
        async with self._uow() as session:
            row = await BrokerRepository(session).by_digest(wanted)
        if row is None or not hmac.compare_digest(row.digest, wanted):
            return None
        if token_state(row, self._clock()) != "live":
            return None
        return TokenGrant(
            run_id=row.run_id,
            connection=row.connection,
            cap_usd=row.cap_usd,
            key_state=row.key_state,
            expires_at=row.expires_at,
        )

    async def end_run(self, run_id: str) -> None:
        """End the run's token: its open streams close, a row without a key goes."""
        async with self._uow() as session:
            repo = BrokerRepository(session)
            row = await repo.end(run_id, self._clock())
            if row is None:
                return
            if row.key_state in ("none", "refused"):
                await repo.delete_without_key(run_id)
        for ended in self._streams.pop(run_id, set()):
            ended.set()
        self._keys.forget(run_id)
        if row.key_state in ("making", "made"):
            self._wake.set()

    async def proxy(self, request: ProxyRequest) -> ProxyAnswer:
        """Answer one run request: send it on with the real credential, or refuse it."""
        if self._stopped:
            return fixed(503, STOPPED_SENTENCE)
        token = token_of(request.headers)
        grant = None if token is None else await self.verify(token)
        if grant is None:
            return fixed(401, NOT_LIVE_SENTENCE)
        return await self._forwarder.forward(grant, request)

    async def receive_telemetry(self, token: str, body: bytes) -> None:
        """Record the model requests in a run's telemetry export.

        Raises:
            TokenRefusedError: not a live run token.
            BadRequestError: the export is not JSON, or not one the sessions module reads.
        """
        grant = await self.verify(token)
        if grant is None:
            raise TokenRefusedError(NOT_LIVE_SENTENCE)
        try:
            export: object = json.loads(body)
        except ValueError:
            raise BadRequestError(NOT_JSON_SENTENCE) from None
        await self._usage.record_run_requests(grant.run_id, export)

    async def sweep(self) -> SweepReport:
        """One housekeeping pass."""
        return await self._sweeper.sweep()

    @staticmethod
    def _info(row: TokenRow, now: datetime) -> TokenInfo:
        return TokenInfo(
            run_id=row.run_id,
            connection=row.connection,
            cap_usd=row.cap_usd,
            key_state=row.key_state,
            ended=token_state(row, now) != "live",
            expires_at=row.expires_at,
            key_delete_error=row.key_delete_error,
        )

    async def describe(self, run_id: str) -> TokenInfo | None:
        """A run's token row without its digest, or `None`."""
        async with self._uow() as session:
            row = await BrokerRepository(session).by_run(run_id)
        return None if row is None else self._info(row, self._clock())

    async def listing(self) -> list[TokenInfo]:
        """The live tokens and the keys waiting to be deleted, oldest first."""
        now = self._clock()
        async with self._uow() as session:
            rows = await BrokerRepository(session).listed(now)
        return [self._info(row, now) for row in rows]

    async def status(self) -> BrokerStatus:
        """Counts for the command line and the health detail."""
        async with self._uow() as session:
            live, held, waiting = await BrokerRepository(session).counts(self._clock())
        return BrokerStatus(
            listening=self._port is not None,
            port=self._port,
            live_tokens=live,
            keys_held=held,
            keys_pending_delete=waiting,
        )

    async def start_run_proxy(self, connection: str) -> RunProxyServer:
        """A CONNECT filter for a container run that reaches only the connection's model host."""
        known = await self._connections.get_connection(connection)
        self._connections.check_rules(known)
        proxy = RunProxyServer(allowed_hosts(self._connections.model_host(known)))
        await proxy.start()
        self._proxies.add(proxy)
        return proxy

    async def serve(self, stop: asyncio.Event) -> None:
        """Run the listener until `stop` is set; open streams are closed and the port released."""
        listener = RunListener(
            BrokerApp(self),
            shutdown_timeout_s=float(self._settings.shutdown_timeout_s),
        )
        self._stopped = False
        self._port = await listener.start()
        self._released = asyncio.Event()
        try:
            await stop.wait()
        finally:
            self._port = None
            self._stopped = True
            await asyncio.shield(self._shut(listener))

    async def _shut(self, listener: RunListener) -> None:
        for ended in [e for events in self._streams.values() for e in events]:
            ended.set()
        await listener.stop()
        for proxy in self._proxies:
            await proxy.stop()
        self._proxies.clear()
        await self.aclose()
        if self._released is not None:
            self._released.set()

    def shutdown(self) -> None:
        """Ask `serve` and `sweep_loop` to end: the app calls this when it stops."""
        self.stopping.set()

    async def released(self) -> None:
        """Wait, within the shutdown limit, until a serving listener has released its port.

        The app's task group cancels its tasks once the stop hooks return; a listener still
        closing then would never finish. Nothing to wait for when the listener never served.
        """
        if self._released is None:
            return
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(float(self._settings.shutdown_timeout_s) + 1):
                await self._released.wait()

    async def aclose(self) -> None:
        """Close the provider client."""
        await self._provider.aclose()

    async def sweep_loop(self, stop: asyncio.Event) -> None:
        """A pass at once, then one every interval or when a run ends holding a key."""
        while not stop.is_set():
            try:
                await self.sweep()
            except Exception:
                logger.exception("a broker sweep failed")
            await self._pause(stop)

    async def _pause(self, stop: asyncio.Event) -> None:
        waiters = {asyncio.ensure_future(stop.wait()), asyncio.ensure_future(self._wake.wait())}
        try:
            await asyncio.wait(
                waiters,
                timeout=self._settings.broker_sweep_interval_s,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for waiter in waiters:
                waiter.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)
            self._wake.clear()
