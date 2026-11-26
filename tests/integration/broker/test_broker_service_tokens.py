"""Issuing, verifying and ending run tokens, and what the listener lets in."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import timedelta
from decimal import Decimal
from typing import override

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from broker_harness import (
    NOW,
    REAL_KEY,
    Builder,
    Clock,
    FakeConnections,
    FakeUsage,
    build,
    issue,
    listening,
)
from broker_support import raw_http
from code_factory.broker.repository import BrokerRepository
from code_factory.broker.rules.tokens import digest
from code_factory.broker.service import BrokerService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, ConflictError, UnavailableError


@pytest.fixture
async def service(
    uow: UnitOfWork, conns: FakeConnections, usage: FakeUsage, clock: Clock
) -> AsyncGenerator[BrokerService]:
    """A listening service over the isolated, rolled back database."""
    conns.add("claude", "anthropic", "http://127.0.0.1:9", key=REAL_KEY)
    made = build(uow, conns, usage, clock)
    task = await listening(made)
    yield made
    made.stopping.set()
    await task
    await made.aclose()


async def test_a_claude_run_gets_the_three_variables_with_an_empty_api_key(
    service: BrokerService,
) -> None:
    issued = await issue(service)
    env = issued.environment
    assert issued.proxy_url == service.endpoints().proxy_url
    assert issued.telemetry_url == issued.proxy_url + "/telemetry"
    assert env["ANTHROPIC_BASE_URL"] == issued.proxy_url
    token = env["ANTHROPIC_AUTH_TOKEN"]
    assert not isinstance(token, str)
    assert token.get_secret_value() == issued.token.get_secret_value()
    assert env["ANTHROPIC_API_KEY"] == ""
    assert set(env) == {"ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"}


async def test_a_telemetry_only_run_gets_a_token_and_no_model_variables(
    service: BrokerService,
) -> None:
    issued = await issue(service, connection=None)
    assert issued.environment == {}
    assert issued.token.get_secret_value().startswith("cfb_")


async def test_a_second_token_for_one_run_is_a_conflict(service: BrokerService) -> None:
    await issue(service)
    with pytest.raises(ConflictError, match=r"^run r1 already holds a broker token$"):
        await issue(service)


async def test_an_unknown_connection_or_a_cap_out_of_range_is_a_bad_request(
    service: BrokerService,
) -> None:
    with pytest.raises(BadRequestError, match="no connection named nope"):
        await issue(service, connection="nope")
    for cap in (Decimal(-1), Decimal(1_000_000)):
        with pytest.raises(BadRequestError, match="under 1000000"):
            await issue(service, "r2", "claude", cap)
    with pytest.raises(BadRequestError, match="a cap needs a connection"):
        await issue(service, "r3", None, Decimal(1))
    assert (await issue(service, "r4", "claude", Decimal("999999.9999"))).token


async def test_a_connection_off_its_rules_is_refused_when_the_token_is_issued(
    service: BrokerService, conns: FakeConnections
) -> None:
    conns.broken.add("claude")
    with pytest.raises(BadRequestError, match="breaks its rules"):
        await issue(service)


async def test_the_row_holds_only_the_digest_of_the_token(
    service: BrokerService, db_session: AsyncSession
) -> None:
    issued = await issue(service)
    token = issued.token.get_secret_value()
    row = await BrokerRepository(db_session).by_digest(digest(token))
    assert row is not None
    assert token not in repr(row)
    assert row.digest == digest(token)


async def test_verify_gives_the_grant_of_a_live_token_and_writes_nothing(
    service: BrokerService, db_session: AsyncSession
) -> None:
    issued = await issue(service, "r1", "claude", Decimal(3))
    grant = await service.verify(issued.token.get_secret_value())
    assert grant is not None
    assert (grant.run_id, grant.connection, grant.cap_usd) == ("r1", "claude", Decimal(3))
    row = await BrokerRepository(db_session).by_run("r1")
    assert row is not None
    assert row.ended_at is None


async def test_verify_refuses_a_token_one_microsecond_past_its_expiry_and_accepts_one_before(
    service: BrokerService, clock: Clock
) -> None:
    issued = await issue(service)
    token = issued.token.get_secret_value()
    clock.now = NOW + timedelta(hours=1) - timedelta(microseconds=1)
    assert await service.verify(token) is not None
    clock.now = NOW + timedelta(hours=1)
    assert await service.verify(token) is None


async def test_ending_a_run_kills_its_token_and_a_row_without_a_key_goes(
    service: BrokerService, db_session: AsyncSession
) -> None:
    issued = await issue(service)
    await service.end_run("r1")
    assert await service.verify(issued.token.get_secret_value()) is None
    assert await BrokerRepository(db_session).by_run("r1") is None
    await service.end_run("r1")  # idempotent
    await service.end_run("never-heard-of")  # a no-op


async def test_describe_shows_a_runs_state_without_digest_token_or_key(
    service: BrokerService,
) -> None:
    issued = await issue(service, "r1", "claude", Decimal("1.5"))
    info = await service.describe("r1")
    assert info is not None
    assert (info.run_id, info.connection, info.cap_usd, info.key_state, info.ended) == (
        "r1",
        "claude",
        Decimal("1.5"),
        "none",
        False,
    )
    assert issued.token.get_secret_value() not in repr(info)
    assert await service.describe("other") is None


async def test_status_counts_live_tokens_and_says_whether_it_listens(
    service: BrokerService,
) -> None:
    await issue(service, "a")
    await issue(service, "b")
    status = await service.status()
    assert (status.listening, status.live_tokens, status.keys_held, status.keys_pending_delete) == (
        True,
        2,
        0,
        0,
    )
    assert status.port == int(service.endpoints().proxy_url.rsplit(":", 1)[1])


async def test_a_malformed_token_is_refused_without_a_database_query(
    uow: UnitOfWork, conns: FakeConnections, usage: FakeUsage, clock: Clock
) -> None:
    opened = 0

    class Counting(UnitOfWork):
        def __init__(self) -> None:
            pass

        @override
        def __call__(self):  # noqa: ANN204
            nonlocal opened
            opened += 1
            return uow()

    conns.add("claude", "anthropic", "http://127.0.0.1:9", key=REAL_KEY)
    counted = build(Counting(), conns, usage, clock)
    task = await listening(counted)
    opened = 0  # `listening` asked for the status
    try:
        port = int(counted.endpoints().proxy_url.rsplit(":", 1)[1])
        for bad in (
            "../x",
            "short",
            "cfb_" + "A" * 42,
            "cfb_" + "A" * 44,
            "x" * 10_000,
        ):
            answer = await raw_http(port, "POST", "/v1/messages", [("x-api-key", bad)], b"{}")
            assert answer.status == 401
        assert opened == 0
        well_formed = await raw_http(
            port, "POST", "/v1/messages", [("x-api-key", "cfb_" + "A" * 43)]
        )
        assert well_formed.status == 401
        assert opened == 1
    finally:
        counted.stopping.set()
        await task
        await counted.aclose()


async def test_endpoints_raise_the_sentence_naming_the_connection_until_the_service_listens(
    uow: UnitOfWork, conns: FakeConnections, usage: FakeUsage, clock: Clock
) -> None:
    idle = build(uow, conns, usage, clock)
    with pytest.raises(UnavailableError) as refused:
        idle.endpoints("main")
    assert str(refused.value) == (
        "no key broker answers: start the board (code-factory serve) to run on connection main"
    )
    await idle.aclose()


async def test_the_listener_is_on_loopback_answers_while_serving_and_is_closed_after_stop(
    make: Builder,
) -> None:
    service = make()
    task = await listening(service)
    url = service.endpoints().proxy_url
    assert url.startswith("http://127.0.0.1:")
    assert service.endpoints().telemetry_url == url + "/telemetry"
    port = int(url.rsplit(":", 1)[1])
    _, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.close()
    await writer.wait_closed()
    service.stopping.set()
    await task
    with pytest.raises(UnavailableError, match="no key broker answers"):
        service.endpoints()
    with pytest.raises(OSError, match=r"refused|Connect"):
        await asyncio.open_connection("127.0.0.1", port)
    assert not (await service.status()).listening
