"""Fakes and builders of the broker tests: connections, usage, run control, a movable clock."""

import asyncio
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import SecretStr

from code_factory.broker.models import BrokerConnection, CodexLogin, IssuedToken
from code_factory.broker.service import BrokerService
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, NotFoundError

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
OFFLINE = "postgresql+asyncpg://nobody:not-a-password@127.0.0.1:1/never_connected"
REAL_KEY = "sk-ant-real-connection-key-000111"
MANAGEMENT_KEY = "sk-or-v1-management-key-000222"
RUN_KEY = "sk-or-v1-run-key-for-one-run-333"
LOGIN_TOKEN = "codex-access-token-444555666"  # noqa: S105  # a fixture value


class Clock:
    """A clock that moves only when a test says so."""

    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def after(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class FakeConnections:
    """The agents module as the broker sees it: connections and keys held in dicts."""

    def __init__(self) -> None:
        self.connections: dict[str, BrokerConnection] = {}
        self.keys: dict[str, str] = {}
        self.broken: set[str] = set()
        self.login: CodexLogin | Exception = CodexLogin(
            access_token=SecretStr(LOGIN_TOKEN), account_id="acct-1"
        )
        self.key_reads: list[str] = []
        self.login_reads = 0

    def add(  # a connection's fields
        self,
        name: str,
        kind: str,
        base_url: str,
        key: str | None = None,
        management: str | None = None,
    ) -> BrokerConnection:
        made = BrokerConnection(
            name=name,
            kind=kind,
            base_url=base_url,
            key_name=f"{name.upper()}_API_KEY" if key is not None else "",
            management_key_name=f"{name.upper()}_MANAGEMENT_API_KEY"
            if management is not None
            else None,
        )
        self.connections[name] = made
        if key is not None:
            self.keys[made.key_name] = key
        if management is not None and made.management_key_name is not None:
            self.keys[made.management_key_name] = management
        return made

    async def get_connection(self, name: str) -> BrokerConnection:
        if name not in self.connections:
            raise NotFoundError("no such connection")
        return self.connections[name]

    def check_rules(self, connection: BrokerConnection) -> None:
        if connection.name in self.broken:
            raise BadRequestError("the connection breaks its rules")

    def model_host(self, connection: BrokerConnection) -> str:
        return connection.base_url.removeprefix("http://").removeprefix("https://").split("/")[0]

    async def read_key(self, name: str) -> SecretStr | None:
        self.key_reads.append(name)
        value = self.keys.get(name)
        return None if value is None else SecretStr(value)

    async def read_codex_login(self) -> CodexLogin:
        self.login_reads += 1
        if isinstance(self.login, Exception):
            raise self.login
        return self.login


class FakeUsage:
    """The sessions module's record of reported requests."""

    def __init__(self) -> None:
        self.recorded: list[tuple[str, object]] = []

    async def record_run_requests(self, run_id: str, export: object) -> None:
        if not isinstance(export, dict):
            raise BadRequestError("the telemetry export must be a JSON object")
        self.recorded.append((run_id, export))


class FakeControl:
    """The runs module's liveness and halt."""

    def __init__(self, active: set[str] | None = None) -> None:
        self.active = active or set()
        self.halted: list[tuple[str, str]] = []

    async def active_run_ids(self, ids: Sequence[str]) -> set[str]:
        return {i for i in ids if i in self.active}

    async def halt_run(self, run_id: str, reason: str) -> None:
        self.halted.append((run_id, reason))


def settings(**more: float) -> Settings:
    """Settings that point nowhere, with the broker's limits as a test lowers them."""
    return Settings(database_url=OFFLINE, _env_file=None, **more)  # ty: ignore[invalid-argument-type]


def build(  # what a test varies
    uow: UnitOfWork,
    connections: FakeConnections,
    usage: FakeUsage,
    clock: Clock,
    **limits: float,
) -> BrokerService:
    return BrokerService(uow, settings(**limits), connections, usage, clock=clock)


async def issue(
    service: BrokerService,
    run: str = "r1",
    connection: str | None = "claude",
    cap: Decimal | None = None,
) -> IssuedToken:
    """A token for the run, valid for an hour after `NOW`."""
    return await service.issue_run_token(run, connection, cap, NOW + timedelta(hours=1))


Builder = Callable[..., BrokerService]


async def listening(service: BrokerService) -> asyncio.Task[None]:
    """Start the service's listener and return its task once it answers."""
    task = asyncio.create_task(service.serve(service.stopping))
    while not (await service.status()).listening:
        if task.done():
            task.result()
        await asyncio.sleep(0.005)
    return task


@asynccontextmanager
async def serving(service: BrokerService) -> AsyncGenerator[BrokerService]:
    """The service listening for the length of the block."""
    task = await listening(service)
    try:
        yield service
    finally:
        service.stopping.set()
        await task
