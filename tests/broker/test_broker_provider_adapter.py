"""The client that sends requests to the provider and the calls that make and delete run keys."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import SecretStr

from broker_support import Receive, Seen, Send, read_all, reply, stand_in
from code_factory.broker.adapters.provider import KeyApi, ProviderClient, UpstreamError
from code_factory.broker.models import (
    WHY_ID,
    WHY_REFUSED,
    WHY_SILENT,
)
from code_factory.broker.rules.keys import run_key_request

MANAGEMENT = SecretStr("sk-or-v1-management-0000")
EXPIRES = datetime(2026, 11, 23, 14, 0, tzinfo=UTC)


async def one_body(data: bytes):  # noqa: ANN201
    yield data


@pytest.fixture
async def client():  # noqa: ANN201
    made = ProviderClient(read_s=0.5, connect_s=2, write_s=2, pool_s=2, max_connections=4)
    yield made
    await made.aclose()


async def test_a_request_goes_with_its_method_target_headers_and_body(
    client: ProviderClient,
) -> None:
    async def handler(seen: Seen, receive: Receive, send: Send) -> None:
        seen.body = await read_all(receive)
        await reply(send, 201, b"made")

    async with stand_in(handler) as provider:
        upstream = await client.stream_request(
            "POST",
            provider.base_url,
            "/v1/messages?beta=true",
            [("x-api-key", "K"), ("content-type", "application/json"), ("content-length", "8")],
            one_body(b'{"a": 1}'),
        )
        try:
            assert upstream.status == 201
            assert b"".join([chunk async for chunk in upstream.chunks()]) == b"made"
        finally:
            await upstream.aclose()
        seen = provider.seen[0]
        assert (seen.method, seen.target, seen.body) == (
            "POST",
            "/v1/messages?beta=true",
            b'{"a": 1}',
        )
        assert seen.header("x-api-key") == ["K"]


async def test_no_header_is_added_to_the_ones_given(client: ProviderClient) -> None:
    async with stand_in() as provider:
        upstream = await client.stream_request(
            "GET", provider.base_url, "/v1/models", [("x-a", "1")]
        )
        await upstream.aclose()
        names = sorted(name for name, _ in provider.seen[0].headers)
        assert names == ["host", "x-a"]


async def test_a_base_path_and_the_target_are_joined_as_two_strings(client: ProviderClient) -> None:
    async with stand_in() as provider:
        upstream = await client.stream_request(
            "GET", provider.base_url + "/api", "/v1/models?x=%2f", []
        )
        await upstream.aclose()
        assert provider.seen[0].target == "/api/v1/models?x=%2f"


async def test_a_response_is_streamed_not_buffered(client: ProviderClient) -> None:
    first_read = asyncio.Event()

    async def handler(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"one", "more_body": True})
        await first_read.wait()
        for part in (b"two", b"three"):
            await send({"type": "http.response.body", "body": part, "more_body": True})
        await send({"type": "http.response.body", "body": b""})

    async with stand_in(handler) as provider:
        try:
            upstream = await client.stream_request("GET", provider.base_url, "/v1/x", [])
            try:
                chunks = upstream.chunks()
                assert await anext(chunks) == b"one"
                first_read.set()
                assert b"".join([chunk async for chunk in chunks]) == b"twothree"
            finally:
                await upstream.aclose()
        finally:
            first_read.set()


async def test_a_redirect_is_returned_and_not_followed(client: ProviderClient) -> None:
    async with stand_in() as elsewhere, stand_in() as provider:

        async def handler(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
            await reply(send, 302, b"", [("location", elsewhere.base_url + "/steal")])

        provider.handler = handler
        upstream = await client.stream_request("GET", provider.base_url, "/v1/x", [])
        await upstream.aclose()
        assert upstream.status == 302
        assert elsewhere.seen == []


async def test_silence_past_the_read_limit_is_an_upstream_error(client: ProviderClient) -> None:
    async def hang(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await asyncio.sleep(5)

    async with stand_in(hang) as provider:
        with pytest.raises(UpstreamError):
            await client.stream_request("GET", provider.base_url, "/v1/x", [])


async def test_a_refused_connection_is_an_upstream_error_without_the_address_in_it(
    client: ProviderClient,
) -> None:
    with pytest.raises(UpstreamError) as error:
        await client.stream_request(
            "GET", "http://127.0.0.1:1", "/v1/x", [("x-api-key", "SECRET-K")]
        )
    assert "127.0.0.1" not in str(error.value)
    assert "SECRET-K" not in str(error.value)


async def test_a_body_stream_that_fails_raises_what_it_raised(client: ProviderClient) -> None:
    async def broken():  # noqa: ANN202
        yield b"x"
        raise ValueError("body ended")

    async with stand_in() as provider:
        given = broken()
        with pytest.raises(ValueError, match="body ended"):
            await client.stream_request("POST", provider.base_url, "/v1/x", [], given)


def api(client: ProviderClient, **more: float) -> KeyApi:
    return KeyApi(client, call_s=more.get("call_s", 0.5))


async def test_a_run_key_is_made_with_the_management_key_as_bearer(client: ProviderClient) -> None:
    async def handler(seen: Seen, receive: Receive, send: Send) -> None:
        seen.body = await read_all(receive)
        await reply(send, 201, b'{"data": {"hash": "h-1"}, "key": "sk-or-v1-runkey-1234"}')

    async with stand_in(handler) as provider:
        body = run_key_request("r1", Decimal(2), EXPIRES)
        result = await api(client).create(provider.base_url + "/api", MANAGEMENT, body)
        seen = provider.seen[0]
    assert result.answered
    assert result.made is not None
    assert (result.made.id, result.made.key.get_secret_value()) == ("h-1", "sk-or-v1-runkey-1234")
    assert (seen.method, seen.target) == ("POST", "/api/v1/keys")
    assert seen.header("authorization") == ["Bearer sk-or-v1-management-0000"]
    assert b'"limit": 2.0' in seen.body or b'"limit":2.0' in seen.body


async def test_a_refused_create_is_an_answer_that_made_nothing(client: ProviderClient) -> None:
    async def handler(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await reply(send, 403, b'{"key": "refused-key-xyz"}')

    async with stand_in(handler) as provider:
        result = await api(client).create(provider.base_url, MANAGEMENT, {"name": "n"})
    assert (result.made, result.answered) == (None, True)


async def test_a_create_that_never_answers_is_not_an_answer(client: ProviderClient) -> None:
    async def hang(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await asyncio.sleep(5)

    async with stand_in(hang) as provider:
        result = await api(client, call_s=0.3).create(provider.base_url, MANAGEMENT, {"name": "n"})
    assert (result.made, result.answered) == (None, False)


@pytest.mark.parametrize("status", [200, 204, 404])
async def test_a_delete_the_provider_accepts_or_does_not_know_is_ok(
    client: ProviderClient, status: int
) -> None:
    async def handler(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await reply(send, status, b"")

    async with stand_in(handler) as provider:
        result = await api(client).delete(provider.base_url, MANAGEMENT, "abc-123")
        seen = provider.seen[0]
    assert result.ok
    assert (seen.method, seen.target) == ("DELETE", "/v1/keys/abc-123")
    assert seen.header("authorization") == ["Bearer sk-or-v1-management-0000"]


async def test_a_delete_answered_with_an_error_says_so_in_a_fixed_sentence(
    client: ProviderClient,
) -> None:
    async def handler(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await reply(send, 500, b"sk-or-v1-management-0000 exploded")

    async with stand_in(handler) as provider:
        result = await api(client).delete(provider.base_url, MANAGEMENT, "abc")
    assert (result.ok, result.why) == (False, WHY_REFUSED)


async def test_a_delete_that_never_answers_says_so_in_a_fixed_sentence(
    client: ProviderClient,
) -> None:
    async def hang(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await asyncio.sleep(5)

    async with stand_in(hang) as provider:
        result = await api(client, call_s=0.3).delete(provider.base_url, MANAGEMENT, "abc")
    assert (result.ok, result.why) == (False, WHY_SILENT)


@pytest.mark.parametrize("key_id", ["", "a/b", "../keys", "a b", "x" * 129, "é", "a?b", "a%2fb"])
async def test_a_key_id_outside_the_pattern_is_never_put_in_a_path(
    client: ProviderClient, key_id: str
) -> None:
    async with stand_in() as provider:
        result = await api(client).delete(provider.base_url, MANAGEMENT, key_id)
        assert provider.seen == []
    assert (result.ok, result.why) == (False, WHY_ID)


async def test_a_key_id_of_the_longest_allowed_length_is_sent(client: ProviderClient) -> None:
    async with stand_in() as provider:
        result = await api(client).delete(provider.base_url, MANAGEMENT, "A-_" + "z" * 125)
    assert result.ok


async def test_at_most_four_calls_are_in_flight_at_once(client: ProviderClient) -> None:
    peak = 0

    async def handler(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        nonlocal peak
        peak = max(peak, provider.live)
        await asyncio.sleep(0.1)
        await reply(send, 204, b"")

    async with stand_in(handler) as provider:
        keys = api(client, call_s=5)
        await asyncio.gather(
            *(keys.delete(provider.base_url, MANAGEMENT, f"k{i}") for i in range(9))
        )
    assert peak == 4


def test_the_client_neither_follows_redirects_nor_reads_the_environment() -> None:
    made = ProviderClient(read_s=1, connect_s=1, write_s=1, pool_s=1, max_connections=4)
    assert made._client.follow_redirects is False
    assert made._client._trust_env is False
