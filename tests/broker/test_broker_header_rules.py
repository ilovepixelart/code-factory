"""Headers: what is never sent on, which credential goes, and what comes back."""

from collections.abc import Callable

import pytest

from code_factory.broker.rules.headers import (
    NOT_SENT_ON,
    credential_header,
    outbound_headers,
    response_headers,
)

# The previous implementation's eleven, written out here and not imported.
PREVIOUS = [
    "host",
    "authorization",
    "x-api-key",
    "proxy-authorization",
    "connection",
    "keep-alive",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
]
ADDED = [
    "cookie",
    "cookie2",
    "forwarded",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
    "chatgpt-account-id",
]


def test_the_set_is_the_eleven_previous_names_and_the_added_ones() -> None:
    assert frozenset(PREVIOUS + ADDED) == NOT_SENT_ON


@pytest.mark.parametrize("name", PREVIOUS + ADDED)
@pytest.mark.parametrize("spelling", [str.lower, str.upper, str.title])
def test_each_name_is_removed_in_any_case_and_every_repeat(
    name: str, spelling: Callable[[str], str]
) -> None:
    sent = outbound_headers(
        [(spelling(name), "a"), ("content-type", "x"), (spelling(name), "b")], ("x-api-key", "K")
    )
    assert [n.lower() for n, _ in sent if n.lower() == name] == (
        ["x-api-key"] if name == "x-api-key" else []
    )
    assert ("content-type", "x") in sent


def test_exactly_one_credential_is_set_and_the_rest_pass_in_order() -> None:
    incoming = [
        ("anthropic-version", "2023-06-01"),
        ("Authorization", "Bearer cfb_token"),
        ("x-api-key", "cfb_token"),
        ("anthropic-beta", "b"),
        ("content-type", "application/json"),
    ]
    assert outbound_headers(incoming, ("x-api-key", "REAL")) == [
        ("anthropic-version", "2023-06-01"),
        ("anthropic-beta", "b"),
        ("content-type", "application/json"),
        ("x-api-key", "REAL"),
    ]


def test_extra_headers_are_set_after_the_credential() -> None:
    sent = outbound_headers(
        [("chatgpt-account-id", "theirs")],
        ("authorization", "Bearer T"),
        extra=(("chatgpt-account-id", "mine"),),
    )
    assert sent == [("authorization", "Bearer T"), ("chatgpt-account-id", "mine")]


def test_anthropic_sends_the_key_as_x_api_key_and_no_bearer() -> None:
    assert credential_header("anthropic", "K") == ("x-api-key", "K")


@pytest.mark.parametrize("kind", ["openrouter", "codex-login", "custom"])
def test_every_other_kind_sends_a_bearer(kind: str) -> None:
    assert credential_header(kind, "K") == ("authorization", "Bearer K")


def test_a_response_drops_hop_by_hop_headers_and_cookies() -> None:
    upstream = [
        ("Connection", "close"),
        ("Keep-Alive", "t"),
        ("Proxy-Authenticate", "x"),
        ("Proxy-Authorization", "x"),
        ("TE", "x"),
        ("Trailer", "x"),
        ("Transfer-Encoding", "chunked"),
        ("Upgrade", "x"),
        ("Set-Cookie", "a=b"),
        ("content-type", "text/event-stream"),
        ("content-encoding", "gzip"),
        ("content-length", "12"),
    ]
    assert response_headers(upstream, []) == [
        ("content-type", "text/event-stream"),
        ("content-encoding", "gzip"),
        ("content-length", "12"),
    ]


def test_a_response_header_holding_a_secret_is_dropped() -> None:
    upstream = [("x-echo", "Bearer real-secret-key"), ("x-other", "fine")]
    assert response_headers(upstream, ["real-secret-key"]) == [("x-other", "fine")]


def test_a_short_secret_does_not_drop_a_header() -> None:
    assert response_headers([("x-a", "abc")], ["abc"]) == [("x-a", "abc")]
