"""Run telemetry on the run listener: checked with the run's token, apart from the proxy."""

from collections.abc import AsyncGenerator

import httpx
import pytest

from broker_harness import REAL_KEY, FakeConnections, FakeUsage, issue
from broker_support import StandIn, stand_in
from code_factory.broker.service import BrokerService

HEADER = "x-code-factory-token"


@pytest.fixture
async def provider(conns: FakeConnections) -> AsyncGenerator[StandIn]:
    async with stand_in() as running:
        conns.add("claude", "anthropic", running.base_url, key=REAL_KEY)
        yield running


def logs(service: BrokerService) -> str:
    return f"{service.endpoints().telemetry_url}/v1/logs"


async def test_a_valid_export_is_recorded_for_its_run_and_answered_with_an_empty_object(
    broker: BrokerService, provider: StandIn, usage: FakeUsage, http: httpx.AsyncClient
) -> None:
    issued = await issue(broker, "r1", "claude")
    export = {"resourceLogs": [{"scopeLogs": []}]}
    answer = await http.post(
        logs(broker), json=export, headers={HEADER: issued.token.get_secret_value()}
    )
    assert (answer.status_code, answer.json()) == (200, {})
    assert usage.recorded == [("r1", export)]
    assert provider.seen == []


async def test_a_token_that_is_missing_unknown_or_ended_is_401_and_records_nothing(
    broker: BrokerService, provider: StandIn, usage: FakeUsage, http: httpx.AsyncClient
) -> None:
    issued = await issue(broker, "r1", "claude")
    token = issued.token.get_secret_value()
    await broker.end_run("r1")
    missing = await http.post(logs(broker), json={})
    unknown = await http.post(logs(broker), json={}, headers={HEADER: "cfb_" + "z" * 43})
    ended = await http.post(logs(broker), json={}, headers={HEADER: token})
    assert {missing.status_code, unknown.status_code, ended.status_code} == {401}
    assert len({missing.content, unknown.content, ended.content}) == 1
    assert usage.recorded == []
    assert provider.seen == []


async def test_a_body_that_is_not_json_is_400(
    broker: BrokerService, usage: FakeUsage, http: httpx.AsyncClient
) -> None:
    issued = await issue(broker, connection=None)
    answer = await http.post(
        logs(broker), content=b"{nope", headers={HEADER: issued.token.get_secret_value()}
    )
    assert answer.status_code == 400
    assert answer.json() == {"error": "the export is not JSON"}
    assert usage.recorded == []


async def test_json_that_is_not_an_object_is_400_from_the_sessions_check(
    broker: BrokerService, usage: FakeUsage, http: httpx.AsyncClient
) -> None:
    issued = await issue(broker, connection=None)
    answer = await http.post(
        logs(broker), json=[1, 2], headers={HEADER: issued.token.get_secret_value()}
    )
    assert answer.status_code == 400
    assert usage.recorded == []


async def test_a_body_over_one_mebibyte_is_413_declared_or_chunked_and_one_at_the_limit_is_taken(
    broker: BrokerService, usage: FakeUsage, http: httpx.AsyncClient
) -> None:
    issued = await issue(broker, connection=None)
    headers = {HEADER: issued.token.get_secret_value()}
    limit = 1024 * 1024
    padding = limit - len(b'{"p": ""}')
    at_limit = b'{"p": "' + b"x" * (padding - 0) + b'"}'
    assert len(at_limit) == limit
    taken = await http.post(logs(broker), content=at_limit, headers=headers)
    assert taken.status_code == 200
    over = await http.post(logs(broker), content=at_limit + b" ", headers=headers)
    assert over.status_code == 413

    async def chunks() -> AsyncGenerator[bytes]:
        for _ in range(3):
            yield b" " * (limit // 2)

    chunked = await http.post(logs(broker), content=chunks(), headers=headers)
    assert chunked.status_code == 413
    assert len(usage.recorded) == 1


async def test_a_path_under_telemetry_other_than_logs_is_404_and_a_get_is_405(
    broker: BrokerService, http: httpx.AsyncClient
) -> None:
    issued = await issue(broker, connection=None)
    headers = {HEADER: issued.token.get_secret_value()}
    base = broker.endpoints().telemetry_url
    assert (await http.post(f"{base}/v1/traces", headers=headers)).status_code == 404
    assert (await http.post(f"{base}/", headers=headers)).status_code == 404
    assert (await http.post(f"{base}/v1/logs/x", headers=headers)).status_code == 404
    got = await http.get(f"{base}/v1/logs", headers=headers)
    assert got.status_code == 405
    assert got.headers["allow"] == "POST"


async def test_a_token_with_a_connection_posting_telemetry_reaches_nothing_of_the_provider(
    broker: BrokerService, provider: StandIn, http: httpx.AsyncClient
) -> None:
    issued = await issue(broker, "r1", "claude")
    await http.post(logs(broker), json={}, headers={HEADER: issued.token.get_secret_value()})
    assert provider.seen == []


@pytest.mark.usefixtures("provider")
async def test_a_proxy_path_never_reaches_the_recorder(
    broker: BrokerService, usage: FakeUsage, http: httpx.AsyncClient
) -> None:
    issued = await issue(broker, "r1", "claude")
    token = issued.token.get_secret_value()
    await http.post(
        f"{broker.endpoints().proxy_url}/v1/logs",
        json={"resourceLogs": []},
        headers={"x-api-key": token, HEADER: token},
    )
    assert usage.recorded == []


async def test_the_proxy_does_not_take_the_telemetry_header_as_a_credential(
    broker: BrokerService, provider: StandIn, http: httpx.AsyncClient
) -> None:
    issued = await issue(broker, "r1", "claude")
    answer = await http.get(
        f"{broker.endpoints().proxy_url}/v1/models",
        headers={HEADER: issued.token.get_secret_value()},
    )
    assert answer.status_code == 401
    assert provider.seen == []
