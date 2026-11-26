"""The module as the app runs it, its command, its adapter, and the main app's silence."""

import argparse
import asyncio
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from agents_support import FakeStore, agents_fixture, clock_fixture, store_fixture  # noqa: F401
from broker_harness import (
    LOGIN_TOKEN,
    MANAGEMENT_KEY,
    NOW,
    REAL_KEY,
    Clock,
    FakeConnections,
    FakeUsage,
    build,
    issue,
    serving,
)
from code_factory.agents.models.connections import ConnectionChange
from code_factory.agents.module import module as agents_module
from code_factory.agents.service import AgentService
from code_factory.app import build_resources, build_services
from code_factory.broker.cli import broker_command
from code_factory.broker.models import BrokerConnection
from code_factory.broker.module import module
from code_factory.broker.repository import BrokerRepository
from code_factory.broker.service import BrokerService
from code_factory.broker.service.neighbours import AgentConnections
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import NotFoundError
from code_factory.platform.runtime import run_on_stop
from code_factory.platform.services import Services
from code_factory.sessions.module import module as sessions_module


async def test_the_module_registers_its_service_and_starts_the_listener_and_the_sweep(
    settings: Settings, tmp_path: Path
) -> None:
    resources = build_resources(settings.model_copy(update={"state_dir": tmp_path}))
    services = build_services(resources, [agents_module, sessions_module, module])
    service = services.get(BrokerService)
    assert module.background is not None
    try:
        async with resources.tasks.run():
            module.background(services, resources.tasks)
            assert sorted(resources.tasks.names) == ["broker-listener", "broker-sweep"]
            async with asyncio.timeout(5):
                while not (await service.status()).listening:  # noqa: ASYNC110  # polls a status
                    await asyncio.sleep(0.01)
            assert service.endpoints().proxy_url.startswith("http://127.0.0.1:")
            await run_on_stop(resources)
            async with asyncio.timeout(5):
                while resources.tasks.names:  # noqa: ASYNC110  # polls the task list
                    await asyncio.sleep(0.01)
    finally:
        await resources.engine.dispose()


async def test_the_main_app_answers_neither_the_telemetry_nor_the_proxy_paths(
    client: httpx.AsyncClient,
) -> None:
    for method, path in (
        ("POST", "/telemetry/v1/logs"),
        ("POST", "/v1/messages"),
        ("POST", "/v1/chat/completions"),
        ("DELETE", "/v1/keys/hash-1"),
    ):
        answer = await client.request(method, path, headers={"x-code-factory-token": "x"})
        assert answer.status_code == 404, (method, path)


def parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="broker")
    broker_command.configure(parser)
    return parser.parse_args(argv)


async def run(service: BrokerService, *argv: str) -> int:
    registry = Services()
    registry.add(BrokerService, service)
    assert broker_command.run_async is not None
    return await broker_command.run_async(parse(*argv), registry)


async def test_status_lists_live_tokens_then_the_keys_waiting_and_never_a_secret(
    uow: UnitOfWork,
    conns: FakeConnections,
    usage: FakeUsage,
    clock: Clock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    conns.add("router", "openrouter", "http://127.0.0.1:9", key=REAL_KEY, management=MANAGEMENT_KEY)
    service = build(uow, conns, usage, clock)
    async with serving(service):
        live = await issue(service, "live", "router", Decimal("2.5"))
        gone = await issue(service, "gone", "router", Decimal(1))
        async with uow() as session:
            repo = BrokerRepository(session)
            await repo.set_state("gone", ("none",), "making", NOW)
            await repo.set_state("gone", ("making",), "made", NOW, "kid-1")
            row = await repo.by_run("gone")
            assert row is not None
            await repo.release_failed(row.id, NOW, "the provider did not answer")
            await repo.end("gone", NOW)
        assert await run(service, "status") == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0] == "run live  connection router  cap $2.5000  key none  live"
    assert lines[1] == (
        "run gone  connection router  cap $1.0000  key made  ended  "
        "waiting to be deleted: the provider did not answer"
    )
    for secret in (
        live.token.get_secret_value(),
        gone.token.get_secret_value(),
        REAL_KEY,
        MANAGEMENT_KEY,
        "kid-1",
    ):
        assert secret not in out


async def test_status_with_nothing_says_so(
    uow: UnitOfWork,
    conns: FakeConnections,
    usage: FakeUsage,
    clock: Clock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert await run(build(uow, conns, usage, clock)) == 0
    assert capsys.readouterr().out == "no live tokens\n"


async def test_sweep_prints_its_counts_and_exits_1_when_a_delete_failed(
    uow: UnitOfWork,
    conns: FakeConnections,
    usage: FakeUsage,
    clock: Clock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    conns.add("router", "openrouter", "http://127.0.0.1:9", key=REAL_KEY, management=MANAGEMENT_KEY)
    service = build(uow, conns, usage, clock)
    assert await run(service, "sweep") == 0
    assert capsys.readouterr().out == "deleted 0, failed 0\n"
    async with serving(service):
        await issue(service, "r1", "router", Decimal(1))
        async with uow() as session:
            repo = BrokerRepository(session)
            await repo.set_state("r1", ("none",), "making", NOW)
            await repo.set_state("r1", ("making",), "made", NOW, "kid-1")
            await repo.end("r1", NOW)
        del conns.connections["router"]  # the key cannot be deleted without its connection
        assert await run(service, "sweep") == 1
    assert capsys.readouterr().out == "deleted 0, failed 1\n"


async def test_the_agents_adapter_reads_a_connection_its_keys_and_the_login_through_the_service(
    agents: AgentService, store: FakeStore, tmp_path: Path
) -> None:
    await agents.add_connection(
        ConnectionChange(
            name="cloud",
            kind="openrouter",
            key_env="OPENROUTER_API_KEY",
            management_key_env="OPENROUTER_MANAGEMENT_API_KEY",
        )
    )
    store.keys["OPENROUTER_API_KEY"] = REAL_KEY
    adapter = AgentConnections(agents)
    connection = await adapter.get_connection("cloud")
    assert connection == BrokerConnection(
        name="cloud",
        kind="openrouter",
        base_url="https://openrouter.ai/api",
        key_name="OPENROUTER_API_KEY",
        management_key_name="OPENROUTER_MANAGEMENT_API_KEY",
    )
    adapter.check_rules(connection)
    assert adapter.model_host(connection) == "openrouter.ai:443"
    key = await adapter.read_key("OPENROUTER_API_KEY")
    assert key is not None
    assert key.get_secret_value() == REAL_KEY
    assert await adapter.read_key("OPENROUTER_MANAGEMENT_API_KEY") is None
    with pytest.raises(NotFoundError):
        await adapter.get_connection("nope")
    folder = tmp_path / "codex"
    folder.mkdir()
    (folder / "auth.json").write_text(
        '{"auth_mode": "chatgpt", "tokens": {"access_token": "'
        + LOGIN_TOKEN
        + '", "account_id": "acct"}}',
        encoding="utf-8",
    )
    login = await adapter.read_codex_login()
    assert (login.access_token.get_secret_value(), login.account_id) == (LOGIN_TOKEN, "acct")
