"""The run proxy's CONNECT head: one method, one exact target."""

import pytest

from code_factory.broker.models import Connect, ConnectRefusal
from code_factory.broker.rules.connect import allowed_hosts, parse_connect

ALLOWED = ["api.anthropic.com:443"]


def head(line: str, tail: str = "Host: api.anthropic.com:443\r\n") -> bytes:
    return f"{line}\r\n{tail}\r\n".encode()


def test_the_allowed_target_is_accepted() -> None:
    assert parse_connect(head("CONNECT api.anthropic.com:443 HTTP/1.1"), ALLOWED) == Connect(
        "api.anthropic.com:443"
    )


def test_the_host_is_compared_in_lowercase() -> None:
    assert parse_connect(head("CONNECT API.Anthropic.COM:443 HTTP/1.0"), ALLOWED) == Connect(
        "api.anthropic.com:443"
    )


def test_another_method_is_405() -> None:
    assert parse_connect(head("GET http://api.anthropic.com/ HTTP/1.1"), ALLOWED) == ConnectRefusal(
        405, "only CONNECT is answered"
    )


@pytest.mark.parametrize(
    "target",
    [
        "evil.example:443",
        "api.anthropic.com:80",
        "a@api.anthropic.com:443",
        "api.anthropic.com:443/x",
        "[::1]:443",
        "api.anthropic.com:0",
        "api.anthropic.com:00443",
        "api.anthropic.com:65536",
        "api.anthropic.com",
        "api.anthropic.com:",
        "api.anthropic.com:+443",
        "api.anthropic.com:44\uff13",
        ":443",
        "127.0.0.1:1",
        "api.anthropic.com:443 ",
    ],
)
def test_any_other_target_is_403(target: str) -> None:
    result = parse_connect(head(f"CONNECT {target} HTTP/1.1"), ALLOWED)
    assert isinstance(result, ConnectRefusal)
    assert result.status == 403


@pytest.mark.parametrize(
    "raw",
    [
        b"CONNECT api.anthropic.com:443 HTTP/1.1\r\n",
        b"CONNECT api.anthropic.com:443 HTTP/2\r\n\r\n",
        b"CONNECT api.anthropic.com:443\r\n\r\n",
        b"CONNECT api.anthropic.com:443 HTTP/1.1\n\n",
        b"",
        b"CONNECT api.anthropic.com:443 HTTP/1.1\r\n" + b"x: y\r\n" * 2000 + b"\r\n",
        b"\xff\xfe\r\n\r\n",
    ],
)
def test_a_head_that_is_not_one_request_line_and_headers_is_dropped(raw: bytes) -> None:
    result = parse_connect(raw, ALLOWED)
    assert isinstance(result, ConnectRefusal)
    assert result.status == 0


def test_the_allowed_list_is_the_connections_model_host() -> None:
    assert allowed_hosts("127.0.0.1:8123") == ["127.0.0.1:8123"]
