"""What a request may ask for: the hostile targets the broker refuses and the ones it sends."""

import pytest

from code_factory.broker.models import Refusal, Target
from code_factory.broker.rules.targets import codex_request_ok, request_target

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
    "/v1/messages\x00",
    "/v1/messages#x",
    "/@evil.example/",
    "*",
    "",
    "/v1",
    "/v1/" + "a" * 5000,
    "/v1/%6beys",
    "/v1/%256Beys/x",
    "/v1/./models",
    "/v1/models/%2E",
    "/v1/mod els",
    "/v1/models\r\nx: y",
    "/v1/models/é",
    "/v1/%2f%2fevil.example",
    "/v1/a%5cb",
    "/v1/%25252e%25252e/keys",
]
GOOD = {
    "/v1/messages?beta=true": "/v1/messages?beta=true",
    "/v1/messages/count_tokens": "/v1/messages/count_tokens",
    "/v1/models": "/v1/models",
    "/v1/chat/completions": "/v1/chat/completions",
    "/v1/models/anthropic/claude-3/endpoints": "/v1/models/anthropic/claude-3/endpoints",
    "/v1/messages?redirect=http://x//y": "/v1/messages?redirect=http://x//y",
}


@pytest.mark.parametrize("target", HOSTILE)
@pytest.mark.parametrize("kind", ["anthropic", "openrouter"])
def test_a_hostile_target_is_refused(kind: str, target: str) -> None:
    assert isinstance(request_target(kind, "POST", target), Refusal)


@pytest.mark.parametrize(("target", "path"), list(GOOD.items()))
@pytest.mark.parametrize("kind", ["anthropic", "openrouter"])
def test_a_provider_path_is_sent_as_written(kind: str, target: str, path: str) -> None:
    assert request_target(kind, "POST", target) == Target(path)
    assert request_target(kind, "GET", target) == Target(path)


def test_the_codex_login_takes_exactly_post_responses_and_drops_the_prefix() -> None:
    assert request_target("codex-login", "POST", "/v1/responses") == Target("/responses")
    assert request_target("codex-login", "POST", "/v1/responses?a=b") == Target("/responses?a=b")


@pytest.mark.parametrize(
    ("method", "target"),
    [
        ("GET", "/v1/responses"),
        ("HEAD", "/v1/responses"),
        ("POST", "/v1/responses/"),
        ("POST", "/v1/responses/.."),
        ("POST", "//v1/responses"),
        ("POST", "/v1/models"),
        ("post", "/v1/responses"),
    ],
)
def test_the_codex_login_refuses_every_other_request(method: str, target: str) -> None:
    assert isinstance(request_target("codex-login", method, target), Refusal)
    assert not codex_request_ok(method, target)


def test_the_codex_check_is_the_one_the_target_uses() -> None:
    assert codex_request_ok("POST", "/v1/responses?x=1")
