"""Run tokens: their form, their digest, where a request carries one and when one is dead."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from code_factory.broker.rules.tokens import digest, new_token, token_of, token_state, well_formed

VALID = "cfb_" + "A" * 43
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def test_a_new_token_is_the_prefix_and_43_url_safe_characters() -> None:
    token = new_token()
    assert re.fullmatch(r"cfb_[A-Za-z0-9_-]{43}", token)
    assert new_token() != token


def test_the_digest_of_a_known_string_is_its_sha256_in_lowercase_hex() -> None:
    # sha256("abc"), FIPS 180-2 appendix B.1
    assert digest("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_a_well_formed_token_is_accepted() -> None:
    assert well_formed(VALID)
    assert well_formed(new_token())


@pytest.mark.parametrize(
    "text",
    [
        "cfb_" + "A" * 42,
        "cfb_" + "A" * 44,
        "cfr_" + "A" * 43,
        "../x",
        "short",
        "cfb_" + "A" * 20 + " " + "A" * 22,
        VALID + "\n",
        "cfb_" + "٣" * 43,
        "cfb_" + "A" * 10_000,
        "",
    ],
)
def test_a_malformed_token_is_refused(text: str) -> None:
    assert not well_formed(text)


def test_bearer_wins_over_x_api_key() -> None:
    headers = [("x-api-key", "second"), ("Authorization", "Bearer first")]
    assert token_of(headers) == "first"


def test_a_bearer_scheme_with_nothing_after_it_is_an_empty_token() -> None:
    assert token_of([("authorization", "Bearer ")]) == ""


def test_the_bearer_scheme_is_case_insensitive() -> None:
    assert token_of([("authorization", "bearer t")]) == "t"


def test_two_spaces_after_the_scheme_are_not_a_bearer_token() -> None:
    assert token_of([("authorization", "Bearer  t")]) is None


def test_only_the_first_of_two_authorization_headers_counts() -> None:
    headers = [("Authorization", "Bearer one"), ("Authorization", "Bearer two")]
    assert token_of(headers) == "one"


def test_x_api_key_is_read_when_there_is_no_bearer() -> None:
    assert token_of([("X-Api-Key", "k"), ("x-api-key", "second")]) == "k"
    assert token_of([("authorization", "Basic abc"), ("x-api-key", "k")]) == "k"
    assert token_of([("accept", "*/*")]) is None


def test_surrounding_whitespace_is_kept_so_a_padded_token_is_malformed() -> None:
    assert token_of([("x-api-key", f" {VALID}")]) == f" {VALID}"
    assert not well_formed(f" {VALID}")


@dataclass
class Row:
    ended_at: datetime | None
    expires_at: datetime


def test_a_token_is_live_until_it_ends_or_expires() -> None:
    assert token_state(Row(None, NOW + timedelta(microseconds=1)), NOW) == "live"
    assert token_state(Row(None, NOW), NOW) == "expired"
    assert token_state(Row(None, NOW - timedelta(microseconds=1)), NOW) == "expired"
    assert token_state(Row(NOW, NOW + timedelta(hours=1)), NOW) == "ended"
    assert token_state(Row(NOW, NOW - timedelta(hours=1)), NOW) == "ended"
