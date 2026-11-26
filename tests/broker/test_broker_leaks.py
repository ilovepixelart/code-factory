"""Nothing that spends money leaves the broker: not in an answer, a log, a row or a repr."""

import gzip
import logging
import os
from collections.abc import AsyncGenerator
from decimal import Decimal

import httpx
import pytest
from pydantic import BaseModel, SecretStr
from sqlalchemy import text

from broker_harness import (
    LOGIN_TOKEN,
    MANAGEMENT_KEY,
    NOW,
    REAL_KEY,
    RUN_KEY,
    FakeConnections,
    FakeControl,
    issue,
)
from broker_router import Router
from broker_support import Receive, Seen, Send, StandIn, reply, stand_in
from code_factory.broker.models import (
    CodexLogin,
    IssuedToken,
    RunKeyMade,
    TokenGrant,
    TokenRefusedError,
)
from code_factory.broker.service import BrokerService
from code_factory.broker.service.vault import RunKeyVault
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError


def secrets_of(token: str) -> list[str]:
    return [token, REAL_KEY, MANAGEMENT_KEY, RUN_KEY, LOGIN_TOKEN]


def assert_clean(text_: str, secrets: list[str]) -> None:
    for secret in secrets:
        assert secret not in text_, "a secret reached the text"


def log_text(caplog: pytest.LogCaptureFixture) -> str:
    """Every message, argument, exception and extra attribute of every record."""
    parts: list[str] = []
    for record in caplog.records:
        parts += [record.getMessage(), str(record.args), record.exc_text or ""]
        parts += [str(value) for value in vars(record).values()]
    return "\n".join(parts)


@pytest.fixture
async def anthropic(conns: FakeConnections) -> AsyncGenerator[StandIn]:
    async with stand_in() as running:
        conns.add("claude", "anthropic", running.base_url, key=REAL_KEY)
        yield running


async def test_an_error_that_echoes_the_key_reaches_the_run_redacted_in_body_and_headers(
    broker: BrokerService, anthropic: StandIn, http: httpx.AsyncClient
) -> None:
    async def echo(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await reply(
            send,
            401,
            f'{{"error": "bad Bearer {REAL_KEY}"}}'.encode(),
            [("x-echo", f"Bearer {REAL_KEY}"), ("x-fine", "ok")],
        )

    anthropic.handler = echo
    issued = await issue(broker)
    answer = await http.get(
        f"{issued.proxy_url}/v1/models", headers={"x-api-key": issued.token.get_secret_value()}
    )
    assert answer.status_code == 401
    assert answer.content == b'{"error": "bad Bearer [redacted]"}'
    assert "x-echo" not in answer.headers
    assert answer.headers["x-fine"] == "ok"
    assert int(answer.headers["content-length"]) == len(answer.content)


async def test_a_success_stream_that_contains_the_key_is_passed_untouched_by_decision(
    broker: BrokerService, anthropic: StandIn, http: httpx.AsyncClient
) -> None:
    """Only error bodies are scrubbed: a model is not expected to be handed the key."""

    async def success(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await reply(send, 200, f"data: {REAL_KEY}".encode())

    anthropic.handler = success
    issued = await issue(broker)
    answer = await http.get(
        f"{issued.proxy_url}/v1/models", headers={"x-api-key": issued.token.get_secret_value()}
    )
    assert answer.content == f"data: {REAL_KEY}".encode()


async def test_a_gzip_error_body_that_echoes_the_key_is_decoded_and_redacted(
    broker: BrokerService, anthropic: StandIn, http: httpx.AsyncClient
) -> None:
    async def echo(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await reply(
            send, 400, gzip.compress(f"bad {REAL_KEY}".encode()), [("content-encoding", "gzip")]
        )

    anthropic.handler = echo
    issued = await issue(broker)
    answer = await http.get(
        f"{issued.proxy_url}/v1/models", headers={"x-api-key": issued.token.get_secret_value()}
    )
    assert answer.status_code == 400
    assert answer.content == b"bad [redacted]"
    assert "content-encoding" not in answer.headers


async def test_an_error_body_in_an_encoding_the_broker_cannot_read_is_replaced_by_a_fixed_sentence(
    broker: BrokerService, anthropic: StandIn, http: httpx.AsyncClient
) -> None:
    async def echo(seen: Seen, receive: Receive, send: Send) -> None:  # noqa: ARG001
        await reply(
            send, 429, b"\x00brotli-bytes" + REAL_KEY.encode(), [("content-encoding", "br")]
        )

    anthropic.handler = echo
    issued = await issue(broker)
    answer = await http.get(
        f"{issued.proxy_url}/v1/models", headers={"x-api-key": issued.token.get_secret_value()}
    )
    assert answer.status_code == 429
    assert REAL_KEY.encode() not in answer.content
    assert b"cannot show" in answer.content


async def test_the_401_and_the_502_bodies_are_byte_equal_whatever_the_cause(
    broker: BrokerService, anthropic: StandIn, conns: FakeConnections, http: httpx.AsyncClient
) -> None:
    issued = await issue(broker)
    headers = {"x-api-key": issued.token.get_secret_value()}
    causes_502 = []
    conns.broken.add("claude")
    causes_502.append(await http.get(f"{issued.proxy_url}/v1/models", headers=headers))
    conns.broken.clear()
    conns.keys.clear()
    causes_502.append(await http.get(f"{issued.proxy_url}/v1/models", headers=headers))
    conns.add("claude", "anthropic", "http://127.0.0.1:1", key=REAL_KEY)
    causes_502.append(await http.get(f"{issued.proxy_url}/v1/models", headers=headers))
    assert {a.status_code for a in causes_502} == {502}
    assert len({a.content for a in causes_502}) == 1
    del anthropic


async def test_with_debug_logging_no_record_holds_a_token_a_key_or_a_login(
    broker: BrokerService,
    conns: FakeConnections,
    http: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
    control: FakeControl,
) -> None:
    router = Router()
    async with stand_in(router) as provider, stand_in() as codex:
        conns.add("claude", "anthropic", provider.base_url, key=REAL_KEY)
        conns.add(
            "router", "openrouter", provider.base_url, key=REAL_KEY, management=MANAGEMENT_KEY
        )
        conns.add("codex", "codex-login", codex.base_url)
        with caplog.at_level(logging.DEBUG):
            plain = await issue(broker, "plain", "claude")
            capped = await issue(broker, "capped", "router", Decimal(2))
            login = await issue(broker, "login", "codex")
            every = [
                (plain, "/v1/models"),
                (capped, "/v1/chat/completions"),
                (login, "/v1/responses"),
                (login, "/v1/models"),  # a refusal
            ]
            for issued, path in every:
                await http.post(
                    f"{issued.proxy_url}{path}",
                    headers={"authorization": f"Bearer {issued.token.get_secret_value()}"},
                    content=b"{}",
                )
            await http.get(f"{plain.proxy_url}/v1/models", headers={"x-api-key": "cfb_" + "q" * 43})
            conns.keys.clear()
            await http.get(
                f"{plain.proxy_url}/v1/models",
                headers={"x-api-key": plain.token.get_secret_value()},
            )
            control.active = set()
            await broker.sweep()
            await broker.end_run("capped")
            conns.keys["ROUTER_MANAGEMENT_API_KEY"] = MANAGEMENT_KEY
            await broker.sweep()
    tokens = [i.token.get_secret_value() for i in (plain, capped, login)]
    assert_clean(log_text(caplog), [*tokens, *secrets_of(tokens[0])])


async def test_the_secrets_show_in_no_repr_str_dump_or_exception_of_the_modules_values(
    broker: BrokerService,
) -> None:
    token_text = "cfb_" + "r" * 43
    token = SecretStr(token_text)
    values: list[object] = [
        IssuedToken(token=token, proxy_url="u", telemetry_url="t", environment={"K": token}),
        TokenGrant(run_id="r", connection="c", cap_usd=None, key_state="none", expires_at=NOW),
        RunKeyMade(id="i", key=SecretStr(RUN_KEY)),
        CodexLogin(access_token=SecretStr(LOGIN_TOKEN), account_id="a"),
        TokenRefusedError("not a live run token"),
        broker,
    ]
    vault = RunKeyVault()
    vault.put("r1", SecretStr(RUN_KEY))
    values.append(vault)
    for value in values:
        shown = [repr(value), str(value)]
        if isinstance(value, BaseModel):
            shown += [str(value.model_dump()), value.model_dump_json()]
        assert_clean("\n".join(shown), [token_text, RUN_KEY, LOGIN_TOKEN, REAL_KEY, MANAGEMENT_KEY])


async def test_after_a_capped_run_no_column_of_the_broker_table_holds_a_secret_or_the_token(
    broker: BrokerService, conns: FakeConnections, http: httpx.AsyncClient, real_uow: UnitOfWork
) -> None:
    router = Router()
    async with stand_in(router) as provider:
        conns.add(
            "router", "openrouter", provider.base_url, key=REAL_KEY, management=MANAGEMENT_KEY
        )
        issued = await issue(broker, "r1", "router", Decimal(2))
        token = issued.token.get_secret_value()
        await http.post(
            f"{issued.proxy_url}/v1/chat/completions",
            headers={"authorization": f"Bearer {token}"},
            content=b"{}",
        )
        async with real_uow() as session:
            dump = "\n".join(
                str(row)
                for row in (
                    await session.execute(text("SELECT broker_tokens::text FROM broker_tokens"))
                ).all()
            )
    assert "hash-1" in dump  # the provider's id for the key is the one thing kept
    assert_clean(dump, secrets_of(token))


async def test_the_broker_never_exports_a_key_to_the_process_environment(
    broker: BrokerService, conns: FakeConnections, http: httpx.AsyncClient
) -> None:
    before = dict(os.environ)
    router = Router()
    async with stand_in(router) as provider:
        conns.add(
            "router", "openrouter", provider.base_url, key=REAL_KEY, management=MANAGEMENT_KEY
        )
        issued = await issue(broker, "r1", "router", Decimal(2))
        await http.post(
            f"{issued.proxy_url}/v1/chat/completions",
            headers={"authorization": f"Bearer {issued.token.get_secret_value()}"},
            content=b"{}",
        )
    assert dict(os.environ) == before


async def test_a_refused_token_error_and_a_bad_export_carry_only_their_sentences(
    broker: BrokerService,
) -> None:
    with pytest.raises(TokenRefusedError, match=r"^not a live run token$"):
        await broker.receive_telemetry("cfb_" + "z" * 43, b"{}")
    issued = await issue(broker, connection=None)
    with pytest.raises(BadRequestError, match=r"^the export is not JSON$"):
        await broker.receive_telemetry(issued.token.get_secret_value(), b"{nope")
