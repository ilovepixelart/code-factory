"""Scrubbing a secret out of what the provider said."""

import gzip
import json
import zlib

import pytest

from code_factory.broker.rules.scrub import ERROR_BODY_LIMIT, error_body, scrub

KEY = "sk-real-key-0123456789"


def naive(data: bytes, secrets: list[str]) -> bytes:
    for secret in sorted(secrets, key=len, reverse=True):
        if len(secret.encode()) >= 8:
            data = data.replace(secret.encode(), b"[redacted]")
    return data


def test_a_key_present_twice_is_replaced_both_times() -> None:
    data = f"a {KEY} b {KEY}".encode()
    assert scrub(data, [KEY]) == b"a [redacted] b [redacted]"


def test_a_key_at_either_edge_is_replaced() -> None:
    assert scrub(KEY.encode(), [KEY]) == b"[redacted]"
    assert scrub(f"x{KEY}".encode(), [KEY]) == b"x[redacted]"


def test_a_key_inside_a_json_string_with_escapes_is_replaced() -> None:
    odd = 'key-with-"quote"-and-\\slash-é'
    body = json.dumps({"error": f"bad {odd}"}).encode()
    assert odd.encode() not in body
    assert b"[redacted]" in scrub(body, [odd])
    assert b"quote" not in scrub(body, [odd])


def test_a_secret_shorter_than_eight_bytes_is_ignored() -> None:
    assert scrub(b"abcdefg abcdefg", ["abcdefg"]) == b"abcdefg abcdefg"
    assert scrub(b"abcdefgh", ["abcdefgh"]) == b"[redacted]"


def test_the_longest_secret_goes_first() -> None:
    longer = KEY + "-tail-xyz"
    assert scrub(longer.encode(), [KEY, longer]) == b"[redacted]"


def test_it_agrees_with_a_naive_replace_loop() -> None:
    secrets = ["secret-aaaa-1", "secret-aaaa-1-more", "other-key-22", "tiny"]
    data = b"x secret-aaaa-1-more y secret-aaaa-1 z other-key-22 tiny"
    assert scrub(data, secrets) == naive(data, secrets)


def gzipped(data: bytes) -> bytes:
    return gzip.compress(data)


def test_an_error_body_is_scrubbed_and_returned_as_it_is_when_it_has_no_encoding() -> None:
    body = f'{{"error": "bad key {KEY}"}}'.encode()
    assert error_body(None, body, [KEY]) == b'{"error": "bad key [redacted]"}'
    assert error_body("identity", body, [KEY]) == b'{"error": "bad key [redacted]"}'


def test_a_gzip_error_body_is_decoded_so_the_key_in_it_is_found() -> None:
    body = gzipped(f"echo {KEY}".encode())
    assert error_body("gzip", body, [KEY]) == b"echo [redacted]"


def test_a_deflate_error_body_is_decoded_too() -> None:
    body = zlib.compress(f"echo {KEY}".encode())
    assert error_body("deflate", body, [KEY]) == b"echo [redacted]"


@pytest.mark.parametrize("encoding", ["br", "zstd", "compress", "gzip, br"])
def test_an_encoding_the_broker_cannot_read_gives_nothing_to_show(encoding: str) -> None:
    assert error_body(encoding, b"whatever", [KEY]) is None


def test_a_gzip_body_that_is_not_gzip_gives_nothing_to_show() -> None:
    assert error_body("gzip", b"not gzip at all", [KEY]) is None


def test_a_gzip_bomb_is_cut_at_the_limit_not_inflated() -> None:
    bomb = gzipped(b"A" * 50_000_000)
    shown = error_body("gzip", bomb, [KEY])
    assert shown is not None
    assert len(shown) == ERROR_BODY_LIMIT


def test_a_body_over_the_limit_is_cut_and_a_key_cut_in_half_at_the_edge_does_not_stay() -> None:
    half = KEY[:10]
    body = b"x" * (ERROR_BODY_LIMIT - 10) + KEY.encode() + b"y" * 100
    shown = error_body(None, body, [KEY])
    assert shown is not None
    assert half.encode() not in shown
    assert len(shown) < ERROR_BODY_LIMIT
