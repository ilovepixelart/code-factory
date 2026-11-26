"""A codex-login connection: the owner's login goes to one path, read for each request alone."""

import logging
from collections.abc import AsyncGenerator
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from broker_harness import LOGIN_TOKEN, FakeConnections, FakeControl, issue
from broker_support import Receive, Seen, Send, StandIn, read_all, reply, stand_in
from code_factory.broker.models import CodexLogin
from code_factory.broker.service import BrokerService
from code_factory.platform.errors import BadRequestError, UnavailableError


@pytest.fixture
async def backend(conns: FakeConnections) -> AsyncGenerator[StandIn]:
    """A stand-in ChatGPT backend as connection `codex` under `/backend-api/codex`."""
    async with stand_in() as running:
        conns.add("codex", "codex-login", running.base_url + "/backend-api/codex")
        yield running


async def post(
    service: BrokerService, token: str, path: str = "/v1/responses?stream=1", method: str = "POST"
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=5) as client:
        return await client.request(
            method,
            f"{service.endpoints().proxy_url}{path}",
            headers={"authorization": f"Bearer {token}", "chatgpt-account-id": "run-own"},
            content=b'{"input": []}',
        )


async def test_a_request_goes_to_the_backend_path_without_v1_with_the_login_and_its_account(
    broker: BrokerService, backend: StandIn
) -> None:
    async def echo(seen: Seen, receive: Receive, send: Send) -> None:
        seen.body = await read_all(receive)
        await reply(send, 200, b"{}")

    backend.handler = echo
    issued = await issue(broker, connection="codex")
    answer = await post(broker, issued.token.get_secret_value())
    assert answer.status_code == 200
    seen = backend.seen[0]
    assert (seen.method, seen.target) == ("POST", "/backend-api/codex/responses?stream=1")
    assert seen.header("authorization") == [f"Bearer {LOGIN_TOKEN}"]
    assert seen.header("chatgpt-account-id") == ["acct-1"]
    assert seen.body == b'{"input": []}'


async def test_the_login_is_read_for_every_request_so_a_change_shows_in_the_next(
    broker: BrokerService, backend: StandIn, conns: FakeConnections
) -> None:
    issued = await issue(broker, connection="codex")
    token = issued.token.get_secret_value()
    await post(broker, token)
    conns.login = CodexLogin(
        access_token=SecretStr("second-login-token-777888"), account_id="acct-2"
    )
    await post(broker, token)
    assert conns.login_reads == 2
    assert [s.header("authorization") for s in backend.seen] == [
        [f"Bearer {LOGIN_TOKEN}"],
        ["Bearer second-login-token-777888"],
    ]
    assert backend.seen[1].header("chatgpt-account-id") == ["acct-2"]


@pytest.mark.parametrize(
    "failure",
    [
        UnavailableError("no codex login at x: run `codex` once on this machine"),
        UnavailableError("the codex login is not a ChatGPT login"),
        BadRequestError("the codex login file does not read as JSON"),
    ],
)
async def test_a_login_that_cannot_be_used_is_502_and_nothing_reaches_the_backend(
    broker: BrokerService, backend: StandIn, conns: FakeConnections, failure: Exception
) -> None:
    conns.login = failure
    issued = await issue(broker, connection="codex")
    answer = await post(broker, issued.token.get_secret_value())
    assert answer.status_code == 502
    assert str(failure).encode() not in answer.content
    assert backend.seen == []


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/responses"),
        ("POST", "/v1/models"),
        ("POST", "/v1/responses/"),
        ("HEAD", "/v1/responses"),
    ],
)
async def test_any_other_request_is_403_with_one_warning_naming_method_and_path_only(
    broker: BrokerService,
    backend: StandIn,
    caplog: pytest.LogCaptureFixture,
    method: str,
    path: str,
) -> None:
    issued = await issue(broker, connection="codex")
    with caplog.at_level(logging.WARNING, logger="code_factory"):
        answer = await post(broker, issued.token.get_secret_value(), f"{path}?secret=query", method)
    assert answer.status_code == 403
    assert backend.seen == []
    ours = [r for r in caplog.records if r.name.startswith("code_factory")]
    assert len(ours) == 1
    text = ours[0].getMessage()
    assert method in text
    assert path in text
    assert "secret=query" not in text
    assert issued.token.get_secret_value() not in text
    assert LOGIN_TOKEN not in text


async def test_a_backend_401_halts_the_run_once_and_still_answers_401_but_a_429_does_not(
    broker: BrokerService, backend: StandIn, control: FakeControl
) -> None:
    issued = await issue(broker, connection="codex")
    token = issued.token.get_secret_value()

    async def deny(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await reply(send, 401, b'{"error": "expired"}')

    backend.handler = deny
    answer = await post(broker, token)
    assert answer.status_code == 401
    assert control.halted == [
        ("r1", "the codex login has expired: run `codex` once on this machine to renew it")
    ]

    async def limited(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await reply(send, 429, b"{}")

    backend.handler = limited
    assert (await post(broker, token)).status_code == 429
    assert len(control.halted) == 1


@pytest.mark.usefixtures("backend")
async def test_a_codex_login_connection_takes_no_cap_and_an_openrouter_one_does(
    broker: BrokerService, conns: FakeConnections
) -> None:
    with pytest.raises(BadRequestError, match="a codex login connection takes no cap"):
        await issue(broker, connection="codex", cap=Decimal(1))
    conns.add("router", "openrouter", "http://127.0.0.1:9", key="k", management="m")
    assert (await issue(broker, "r2", "router", Decimal(1))).token.get_secret_value()
