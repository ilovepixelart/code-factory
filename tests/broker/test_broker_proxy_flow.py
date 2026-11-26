"""What reaches the provider through the run listener: the real key and nothing of the run's."""

import asyncio
import time
from collections.abc import AsyncGenerator

import httpx
import pytest

from broker_harness import REAL_KEY, Builder, Clock, FakeConnections, issue, listening
from broker_support import (
    Receive,
    Seen,
    Send,
    StandIn,
    raw_http,
    read_all,
    reply,
    stand_in,
    stream_forever,
)
from code_factory.broker.service import BrokerService
from code_factory.broker.service.exchange import ProxyRequest


@pytest.fixture
async def provider(conns: FakeConnections) -> AsyncGenerator[StandIn]:
    """A stand-in Anthropic, as connection `claude` with its key."""
    async with stand_in() as running:
        conns.add("claude", "anthropic", running.base_url, key=REAL_KEY)
        yield running


def proxy_port(broker: BrokerService) -> int:
    return int(broker.endpoints().proxy_url.rsplit(":", 1)[1])


async def test_a_live_runs_request_reaches_the_provider_with_the_real_key_and_nothing_of_its_own(
    broker: BrokerService, provider: StandIn, http: httpx.AsyncClient
) -> None:
    async def echo(seen: Seen, receive: Receive, send: Send) -> None:
        seen.body = await read_all(receive)
        await reply(send, 200, b'{"id": "msg_1"}')

    provider.handler = echo
    issued = await issue(broker)
    token = issued.token.get_secret_value()
    answer = await http.post(
        f"{issued.proxy_url}/v1/messages?beta=true",
        headers={"authorization": f"Bearer {token}", "anthropic-version": "2023-06-01"},
        content=b'{"model": "m"}',
    )
    assert (answer.status_code, answer.content) == (200, b'{"id": "msg_1"}')
    seen = provider.seen[0]
    assert (seen.method, seen.target, seen.body) == (
        "POST",
        "/v1/messages?beta=true",
        b'{"model": "m"}',
    )
    assert seen.header("x-api-key") == [REAL_KEY]
    assert seen.header("authorization") == []
    assert seen.header("anthropic-version") == ["2023-06-01"]
    assert token.encode() not in seen.everything()


async def test_the_tokens_of_a_dead_run_all_get_one_identical_401_and_reach_nothing(
    broker: BrokerService, provider: StandIn
) -> None:
    issued = await issue(broker, "ended")
    await broker.end_run("ended")
    other = await issue(broker, "expiring")
    port = proxy_port(broker)
    answers = [
        await raw_http(port, "POST", "/v1/messages", [("authorization", f"Bearer {t}")], b"{}")
        for t in (
            issued.token.get_secret_value(),  # ended
            "cfb_" + "z" * 43,  # unknown
            other.token.get_secret_value() + "x",  # malformed
        )
    ]
    assert {a.status for a in answers} == {401}
    assert len({a.body for a in answers}) == 1
    assert provider.seen == []


async def test_an_expired_token_is_401(
    broker: BrokerService, provider: StandIn, http: httpx.AsyncClient, clock: Clock
) -> None:
    issued = await issue(broker)
    clock.after(hours=2)
    answer = await http.post(
        f"{issued.proxy_url}/v1/messages", headers={"x-api-key": issued.token.get_secret_value()}
    )
    assert answer.status_code == 401
    assert provider.seen == []


async def test_a_run_that_sends_headers_of_its_own_does_not_get_them_through(
    broker: BrokerService, provider: StandIn
) -> None:
    issued = await issue(broker)
    token = issued.token.get_secret_value()
    await raw_http(
        proxy_port(broker),
        "POST",
        "/v1/messages",
        [
            ("authorization", f"Bearer {token}"),
            ("Authorization", "Bearer second"),
            ("x-api-key", "run-own-key"),
            ("Proxy-Authorization", "Basic abc"),
            ("Cookie", "session=1"),
            ("X-Forwarded-For", "6.6.6.6"),
            ("Forwarded", "for=6.6.6.6"),
            ("x-real-ip", "6.6.6.6"),
            ("anthropic-beta", "b1"),
        ],
        b"{}",
    )
    seen = provider.seen[0]
    names = {name for name, _ in seen.headers}
    assert {
        "authorization",
        "proxy-authorization",
        "cookie",
        "x-forwarded-for",
        "forwarded",
        "x-real-ip",
    }.isdisjoint(names)
    assert seen.header("x-api-key") == [REAL_KEY]
    assert seen.header("anthropic-beta") == ["b1"]


HOSTILE = [
    "//evil.example/v1/messages",
    "/v1/../v1/keys",
    "/v1/%2e%2e/keys",
    "/v1/%2E%2E%2Fkeys",
    "/v1/%252e%252e/keys",
    "/v1/keys",
    "/v1/keys/abc",
    "/V1/keys",
    "http://evil.example/v1/messages",
    "/v1/messages\\..\\keys",
    "/v1/messages%00",
    "/@evil.example/",
    "*",
    "/v1",
    "/v1/" + "a" * 5000,
]


@pytest.mark.parametrize("target", HOSTILE)
async def test_a_hostile_target_is_403_and_neither_provider_hears_of_it(
    broker: BrokerService, provider: StandIn, target: str
) -> None:
    async with stand_in() as evil:
        issued = await issue(broker)
        answer = await raw_http(
            proxy_port(broker),
            "GET",
            target,
            [("x-api-key", issued.token.get_secret_value())],
        )
        assert answer.status in {400, 403, 404}
        if answer.status == 403:
            assert b"does not send" in answer.body
        assert provider.seen == []
        assert evil.seen == []


async def test_a_redirect_reaches_the_run_unfollowed(
    broker: BrokerService, provider: StandIn, http: httpx.AsyncClient
) -> None:
    async with stand_in() as elsewhere:

        async def redirect(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
            await reply(send, 302, b"", [("location", elsewhere.base_url + "/steal")])

        provider.handler = redirect
        issued = await issue(broker)
        answer = await http.get(
            f"{issued.proxy_url}/v1/models",
            headers={"x-api-key": issued.token.get_secret_value()},
            follow_redirects=False,
        )
        assert answer.status_code == 302
        assert answer.headers["location"] == elsewhere.base_url + "/steal"
        assert elsewhere.seen == []


async def test_a_response_streams_in_chunks_as_the_provider_sends_them_and_stays_encoded(
    broker: BrokerService, provider: StandIn
) -> None:
    gzip_bytes = b"\x1f\x8b\x08\x00not-really-gzip"

    async def slow(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/event-stream"),
                    (b"content-encoding", b"gzip"),
                ],
            }
        )
        for part in (gzip_bytes, b"two", b"three"):
            await send({"type": "http.response.body", "body": part, "more_body": True})
            await asyncio.sleep(0.2)
        await send({"type": "http.response.body", "body": b""})

    provider.handler = slow
    issued = await issue(broker)
    async with httpx.AsyncClient(timeout=5) as client:
        started = time.monotonic()
        arrivals: list[tuple[bytes, float]] = []
        async with client.stream(
            "POST",
            f"{issued.proxy_url}/v1/messages",
            headers={"x-api-key": issued.token.get_secret_value()},
        ) as answer:
            assert answer.headers["content-encoding"] == "gzip"
            arrivals.extend([(c, time.monotonic() - started) async for c in answer.aiter_raw()])
    assert b"".join(chunk for chunk, _ in arrivals) == gzip_bytes + b"twothree"
    assert arrivals[0][1] < 0.18
    assert arrivals[-1][1] >= 0.4


async def test_a_client_that_disconnects_mid_stream_closes_the_provider_side_quickly(
    broker: BrokerService, provider: StandIn
) -> None:
    provider.handler = stream_forever
    issued = await issue(broker)
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port(broker))
    token = issued.token.get_secret_value()
    writer.write(f"GET /v1/stream HTTP/1.1\r\nHost: x\r\nx-api-key: {token}\r\n\r\n".encode())
    await writer.drain()
    assert await asyncio.wait_for(reader.read(64), 3)
    writer.close()
    await asyncio.wait_for(provider.seen[0].closed.wait(), 1.5)
    assert provider.live == 0


async def test_ending_the_run_closes_its_open_stream_within_a_second_and_kills_the_token(
    broker: BrokerService, provider: StandIn
) -> None:
    provider.handler = stream_forever
    issued = await issue(broker)
    token = issued.token.get_secret_value()
    async with (
        httpx.AsyncClient(timeout=5) as client,
        client.stream("GET", f"{issued.proxy_url}/v1/x", headers={"x-api-key": token}) as answer,
    ):
        iterator = answer.aiter_raw()
        await anext(iterator)
        await broker.end_run("r1")
        started = time.monotonic()
        async for _ in iterator:
            pass
        assert time.monotonic() - started < 1
        again = await client.get(f"{issued.proxy_url}/v1/x", headers={"x-api-key": token})
    assert again.status_code == 401
    await asyncio.wait_for(provider.seen[0].closed.wait(), 1.5)


@pytest.mark.usefixtures("provider")
async def test_a_body_over_the_limit_is_413_whether_its_length_is_declared_or_chunked(
    make: Builder, http: httpx.AsyncClient
) -> None:
    service = make(broker_max_body_mib=1)
    task = await listening(service)
    try:
        issued = await issue(service)
        headers = {"x-api-key": issued.token.get_secret_value()}
        declared = await http.post(
            f"{issued.proxy_url}/v1/messages", headers=headers, content=b"x" * (2 * 1024 * 1024)
        )
        assert declared.status_code == 413

        async def chunks() -> AsyncGenerator[bytes]:
            for _ in range(4):
                yield b"x" * (512 * 1024)

        chunked = await http.post(
            f"{issued.proxy_url}/v1/messages", headers=headers, content=chunks()
        )
        assert chunked.status_code == 413
        assert chunked.content == declared.content
        small = await http.post(
            f"{issued.proxy_url}/v1/messages", headers=headers, content=b"x" * 1000
        )
        assert small.status_code == 200
    finally:
        service.stopping.set()
        await task


async def test_every_failure_on_the_way_is_one_502_with_a_fixed_body(
    broker: BrokerService, conns: FakeConnections, http: httpx.AsyncClient
) -> None:
    conns.add("claude", "anthropic", "http://127.0.0.1:1", key=REAL_KEY)  # nothing listens there
    issued = await issue(broker)
    headers = {"x-api-key": issued.token.get_secret_value()}
    unreachable = await http.get(f"{issued.proxy_url}/v1/models", headers=headers)
    conns.keys.clear()  # the connection's key is gone
    no_key = await http.get(f"{issued.proxy_url}/v1/models", headers=headers)
    assert {unreachable.status_code, no_key.status_code} == {502}
    assert unreachable.content == no_key.content
    assert b"127.0.0.1" not in unreachable.content
    assert REAL_KEY.encode() not in unreachable.content


async def test_a_provider_that_hangs_past_the_read_limit_is_a_502_and_sends_nothing_more(
    make: Builder, conns: FakeConnections, http: httpx.AsyncClient
) -> None:
    async def hang(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await asyncio.sleep(10)

    async with stand_in(hang) as slow:
        conns.add("claude", "anthropic", slow.base_url, key=REAL_KEY)
        service = make(broker_read_timeout_s=0.3)
        task = await listening(service)
        try:
            issued = await issue(service)
            answer = await http.get(
                f"{issued.proxy_url}/v1/models",
                headers={"x-api-key": issued.token.get_secret_value()},
            )
        finally:
            service.stopping.set()
            await task
    assert answer.status_code == 502
    assert b"could not send" in answer.content


async def test_a_connection_gone_mid_run_is_401_and_one_off_its_rules_is_502_and_nothing_is_sent(
    broker: BrokerService, provider: StandIn, conns: FakeConnections, http: httpx.AsyncClient
) -> None:
    issued = await issue(broker)
    headers = {"x-api-key": issued.token.get_secret_value()}
    conns.broken.add("claude")
    off_rules = await http.get(f"{issued.proxy_url}/v1/models", headers=headers)
    conns.broken.clear()
    del conns.connections["claude"]
    gone = await http.get(f"{issued.proxy_url}/v1/models", headers=headers)
    assert (off_rules.status_code, gone.status_code) == (502, 401)
    assert provider.seen == []


async def test_a_token_without_a_connection_is_403_for_the_proxy(
    broker: BrokerService, provider: StandIn, http: httpx.AsyncClient
) -> None:
    issued = await issue(broker, connection=None)
    answer = await http.get(
        f"{issued.proxy_url}/v1/models", headers={"x-api-key": issued.token.get_secret_value()}
    )
    assert answer.status_code == 403
    assert provider.seen == []


async def test_a_stopped_service_answers_503_to_what_is_still_in_flight(
    broker: BrokerService,
) -> None:
    assert (await broker.proxy(ProxyRequest("GET", "/v1/x", []))).status == 401
    broker.stopping.set()
    await asyncio.sleep(0.3)
    assert (await broker.proxy(ProxyRequest("GET", "/v1/x", []))).status == 503
