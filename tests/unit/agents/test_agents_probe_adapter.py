"""The model server adapter against stub servers on loopback: statuses, silence, a refused port,
a redirect that must not be followed and a proxy variable that must be ignored."""

import json

import pytest
from pydantic import SecretStr

from code_factory.agents.adapters.probe import ModelProbe
from code_factory.agents.models.connections import (
    ConnectionDefinition,
    Found,
    Model,
    Silence,
    Status,
)
from code_factory.agents.rules.model_checks import Ask, Request
from stub_server import closed_address, respond, serve

OLLAMA_LIST = json.dumps({"models": [{"name": "qwen"}]})
OLLAMA_PS = json.dumps({"models": [{"name": "qwen", "context_length": 65536}]})


def probe(**limits: float) -> ModelProbe:
    return ModelProbe(**limits)


async def test_a_200_answers_with_its_body() -> None:
    async with serve(lambda _: respond("200 OK", "[1]")) as stub:
        assert await probe().get(f"{stub.address}/x", {}) == (200, "[1]")
        assert stub.heads()[0].startswith("GET /x HTTP/1.1")


async def test_a_500_answers_with_its_status_and_body() -> None:
    async with serve(lambda _: respond("500 Internal Server Error", "boom")) as stub:
        assert await probe().get(stub.address, {}) == (500, "boom")


async def test_a_server_that_holds_the_request_is_no_answer_after_the_limit() -> None:
    async with serve(lambda _: None) as stub:
        assert await probe(probe_s=0.3).get(stub.address, {}) is Silence.NO_ANSWER


async def test_a_closed_port_is_connection_refused() -> None:
    assert await probe().get(closed_address(), {}) is Silence.REFUSED


async def test_an_address_that_does_not_resolve_is_no_answer_not_refused() -> None:
    assert await probe().get("http://nothing.invalid", {}) is Silence.NO_ANSWER


async def test_a_redirect_is_not_followed() -> None:
    async with serve(lambda _: respond("200 OK", "{}")) as target:
        location = f"Location: {target.address}/stolen\r\n"
        async with serve(lambda _: respond("302 Found", "", headers=location)) as first:
            assert await probe().get(first.address, {"x-api-key": "sk-1"}) == (302, "")
        assert target.requests == []


async def test_a_proxy_variable_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    async with serve(lambda _: respond("200 OK", "{}")) as proxy:
        monkeypatch.setenv("HTTP_PROXY", proxy.address)
        monkeypatch.setenv("http_proxy", proxy.address)
        monkeypatch.setenv("ALL_PROXY", proxy.address)
        async with serve(lambda _: respond("200 OK", "direct")) as server:
            assert await probe().get(server.address, {}) == (200, "direct")
        assert proxy.requests == []


async def test_a_key_travels_only_in_a_header() -> None:
    async with serve(lambda _: respond("200 OK", "{}")) as stub:
        await probe().get(f"{stub.address}/v1/models", {"x-api-key": "sk-secret"})
        head, body = stub.requests[0]
        assert "x-api-key: sk-secret" in head
        assert "sk-secret" not in head.splitlines()[0]
        assert body == ""


async def test_a_check_posts_its_json_body_and_headers() -> None:
    request = Request(Ask.TOOL, "", ["content-type: application/json", "x-extra: 1"], {"a": 1})
    async with serve(lambda _: respond("200 OK", '{"ok":true}')) as stub:
        sent = Request(request.ask, f"{stub.address}/v1/messages", request.headers, request.body)
        assert await probe().ask(sent) == (200, '{"ok":true}')
        head, body = stub.requests[0]
        assert head.startswith("POST /v1/messages HTTP/1.1")
        assert "x-extra: 1" in head
        assert json.loads(body) == {"a": 1}


async def test_a_check_that_gets_no_answer_in_its_limit_is_no_answer() -> None:
    async with serve(lambda _: None) as stub:
        sent = Request(Ask.JSON, f"{stub.address}/v1/chat/completions", [], {})
        assert await probe(check_s=0.3).ask(sent) is Silence.NO_ANSWER


def local(kind: str, base_url: str) -> ConnectionDefinition:
    return ConnectionDefinition(name="c", kind=kind, base_url=base_url)


async def test_ollama_models_come_with_the_context_they_are_loaded_with() -> None:
    def answer(head: str) -> str:
        return respond("200 OK", OLLAMA_PS if "/api/ps" in head else OLLAMA_LIST)

    async with serve(answer) as stub:
        status = await probe().status(local("ollama", stub.address), None)
        assert status == Status(
            name="c", answers=True, models=[Model(id="qwen", loaded=65536)], problem=""
        )


async def test_a_status_words_an_http_error_a_refusal_and_silence() -> None:
    async with serve(lambda _: respond("503 Service Unavailable", "")) as stub:
        status = await probe().status(local("custom", stub.address), None)
        assert (status.answers, status.problem) == (False, "HTTP 503")
    refused = await probe().status(local("custom", closed_address()), None)
    assert (refused.answers, refused.problem) == (False, "connection refused")
    async with serve(lambda _: None) as stub:
        silent = await probe(probe_s=0.3).status(local("custom", stub.address), None)
        assert (silent.answers, silent.problem) == (False, "no answer")


async def test_a_status_refuses_an_address_that_breaks_the_rules_without_asking() -> None:
    async with serve(lambda _: respond("200 OK", "{}")) as stub:
        status = await probe().status(local("ollama", "http://10.0.0.5:11434"), None)
        assert status.answers is False
        assert status.problem.startswith("ollama connections run on this machine")
        assert stub.requests == []


async def test_a_keyed_connection_without_its_key_is_not_asked() -> None:
    cloud = ConnectionDefinition(
        name="cloud",
        kind="openrouter",
        base_url="https://openrouter.ai/api",
        key_env="OPENROUTER_API_KEY",
    )
    status = await probe().status(cloud, None)
    assert (status.answers, status.problem) == (False, "OPENROUTER_API_KEY is not set")
    assert await probe().status(cloud, SecretStr("")) == status


async def test_local_servers_that_answer_are_found_with_their_state_and_models() -> None:
    async with (
        serve(lambda _: respond("200 OK", OLLAMA_LIST)) as one,
        serve(lambda _: respond("503 Service Unavailable", "")) as two,
    ):
        found = await probe().local(
            [
                ("ollama", one.address, "/api/tags"),
                ("llama-cpp", two.address, "/health"),
                ("lm-studio", closed_address(), "/api/v0/models"),
            ]
        )
    assert found == [
        Found(kind="ollama", base_url=one.address, state="answers", models=[Model(id="qwen")]),
        Found(kind="llama-cpp", base_url=two.address, state="loading a model", models=[]),
    ]


async def test_a_body_that_does_not_decode_is_no_answer() -> None:
    async with serve(
        lambda _: respond("200 OK", "plain", headers="content-encoding: gzip\r\n")
    ) as stub:
        assert await probe().get(stub.address, {}) is Silence.NO_ANSWER
        assert await probe().local([("llama-cpp", stub.address, "/health")]) == []
        status = await probe().status(local("custom", stub.address), None)
        assert (status.answers, status.problem) == (False, "no answer")


async def test_an_answer_is_cut_at_four_mebibytes() -> None:
    big = "x" * (4 * 1024 * 1024 + 1000)
    async with serve(lambda _: respond("200 OK", big)) as stub:
        answer = await probe().get(stub.address, {})
        assert not isinstance(answer, Silence)
        status, body = answer
        assert (status, len(body)) == (200, 4 * 1024 * 1024)
