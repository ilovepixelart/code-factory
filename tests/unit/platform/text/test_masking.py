from collections.abc import Callable

import pytest

from code_factory.platform.text import REDACTED, masked
from growth import LINEAR_BOUND, growth

KEYS = ["token", "api_key", "api-key", "apikey", "secret", "password", "passwd"]


@pytest.mark.parametrize("key", KEYS)
def test_a_json_quoted_secret_is_masked_and_its_key_kept(key: str) -> None:
    assert masked(f'{{"{key}": "abc123"}}') == f'{{"{key}": "[redacted]"}}'
    assert masked(f'{{"user":"jo","{key}":"abc123","n":1}}') == (
        f'{{"user":"jo","{key}":"[redacted]","n":1}}'
    )


@pytest.mark.parametrize("key", KEYS)
def test_an_escaped_json_secret_is_masked(key: str) -> None:
    assert masked(rf"{{\"{key}\":\"abc123\"}}") == rf"{{\"{key}\":\"[redacted]\"}}"
    assert masked(rf"{{\"{key}\": \"abc123\", \"n\": 1}}") == (
        rf"{{\"{key}\": \"[redacted]\", \"n\": 1}}"
    )


@pytest.mark.parametrize("key", KEYS)
def test_a_doubly_and_triply_escaped_json_secret_is_masked(key: str) -> None:
    assert masked(rf"{{\\\"{key}\\\":\\\"abc123\\\"}}") == rf"{{\\\"{key}\\\":\\\"[redacted]\\\"}}"
    triple = r"\\\\\\\""
    assert masked(f"{triple}{key}{triple}: {triple}abc123{triple}") == (
        f"{triple}{key}{triple}: {triple}[redacted]{triple}"
    )


def test_an_escaped_value_with_spaces_inside_a_triple_escaped_pair_is_masked_whole() -> None:
    assert masked(r"{\\\"token\\\":\\\"ab\\\\/cd x\\\",\\\"n\\\":1}") == (
        r"{\\\"token\\\":\\\"[redacted]\\\",\\\"n\\\":1}"
    )


def test_an_authorization_header_value_is_masked_whole() -> None:
    assert masked('{"authorization": "Bearer abc123"}') == '{"authorization": "[redacted]"}'
    assert masked('{"Authorization":"Bearer abc123","n":1}') == (
        '{"Authorization":"[redacted]","n":1}'
    )
    assert masked(r"{\"authorization\":\"Bearer abc123\"}") == (
        r"{\"authorization\":\"[redacted]\"}"
    )
    assert masked(r"{\\\"authorization\\\":\\\"Bearer abc123\\\"}") == (
        r"{\\\"authorization\\\":\\\"[redacted]\\\"}"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (r'{"token": "ab\/cd"}', '{"token": "[redacted]"}'),
        (r'{"password": "ab\\cd", "n": 1}', '{"password": "[redacted]", "n": 1}'),
        (r'{"secret": "a\"b"}', '{"secret": "[redacted]"}'),
        (r'{"token": "ab\\"}', '{"token": "[redacted]"}'),
        (r"{\"token\":\"ab\\/cd\"}", r"{\"token\":\"[redacted]\"}"),
        ("token=ab\\cd next", "token=[redacted] next"),
        ("password: 'ab\\'cd' next", "password: '[redacted]' next"),
        ("authorization: Bearer ab\\cd next", "authorization: [redacted] next"),
        (r'{"authorization": "Bearer ab\/cd"}', '{"authorization": "[redacted]"}'),
    ],
)
def test_an_escape_sequence_stays_inside_the_masked_value(text: str, expected: str) -> None:
    assert masked(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"password": "two words, three; four", "n": 1}', '{"password": "[redacted]", "n": 1}'),
        (
            r"{\"password\":\"two words, x\",\"n\":1}",
            r"{\"password\":\"[redacted]\",\"n\":1}",
        ),
        ("password: 'two words' next", "password: '[redacted]' next"),
        ('{"authorization": "Bearer ab, cd", "n": 1}', '{"authorization": "[redacted]", "n": 1}'),
        ("token=abc,next", "token=[redacted],next"),
        ("token=abc;next", "token=[redacted];next"),
    ],
)
def test_a_quoted_value_runs_to_its_closing_quote_and_a_bare_one_ends_at_a_separator(
    text: str, expected: str
) -> None:
    assert masked(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "nothing secret here",
        "the token expired; ask for a new secret and reset the password",
        "Authorization failed for this request",
        '{"name": "jo", "count": 3, "tags": ["a", "b"], "ok": true}',
        '{"message": "the token was refused", "kind": "secret"}',
        r"{\"message\":\"the token was refused\",\"n\":1}",
        '{"note": "a \\"quoted\\" word, then more", "token": ""}',
        '{"usage": {"input_tokens": 12, "output_tokens": 3}, "secretary": "Jo"}',
        "AKIA" + "A" * 15,
    ],
)
def test_text_without_a_secret_is_unchanged(text: str) -> None:
    assert masked(text) == text


def test_bare_forms_are_masked() -> None:
    assert masked("token=abc123 next") == "token=[redacted] next"
    assert masked("password: 'abc123'") == "password: '[redacted]'"
    assert masked("authorization: Bearer abc123 next") == "authorization: [redacted] next"


def test_key_shapes_are_masked_whole() -> None:
    assert masked("use sk-abcDEF123_x-y now") == f"use {REDACTED} now"
    assert masked("ghp_abc123 and gho_x9 and xoxb-1-2 and xoxp-3") == (
        f"{REDACTED} and {REDACTED} and {REDACTED} and {REDACTED}"
    )
    assert masked("key AKIAABCDEFGHIJKLMNOP end") == f"key {REDACTED} end"


def test_a_key_shape_is_not_masked_inside_a_word() -> None:
    assert masked("task-list and sk") == "task-list and sk"


@pytest.mark.parametrize(
    "shape",
    [
        lambda n: "token" + "\\" * n,
        lambda n: "authorization:" + " a" * n,
        lambda n: 'token="' + "\\" * n,
    ],
)
def test_pathological_input_is_masked_in_linear_time(shape: Callable[[int], str]) -> None:
    assert growth(lambda n: masked(shape(n)), 5_000) < LINEAR_BOUND


def test_a_literal_quote_inside_a_nested_json_value_does_not_end_it() -> None:
    once = r"{\"password\":\"ab\\\"cd\",\"n\":1}"
    assert masked(once) == r"{\"password\":\"[redacted]\",\"n\":1}"
    thrice = r"{\\\"password\\\":\\\"ab\\\\\\\"cd\\\",\\\"n\\\":1}"
    assert masked(thrice) == r"{\\\"password\\\":\\\"[redacted]\\\",\\\"n\\\":1}"
