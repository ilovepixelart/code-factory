"""The run key request and what counts as the provider having made one."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from code_factory.broker.rules.keys import run_key_made, run_key_request

EXPIRES = datetime(2026, 11, 23, 14, 30, 5, 123456, tzinfo=UTC)


def test_the_request_names_the_run_limits_the_cap_and_ends_with_the_run() -> None:
    body = run_key_request("r-1", Decimal("2.5"), EXPIRES)
    assert body == {
        "name": "code-factory run r-1",
        "limit": 2.5,
        "expires_at": "2026-11-23T14:30:05Z",
    }
    assert isinstance(body["limit"], float)
    assert json.dumps(body)


def test_a_created_key_with_its_hash_is_made() -> None:
    made = run_key_made(201, {"data": {"hash": "abc123"}, "key": "sk-or-v1-1234567890"})
    assert made is not None
    assert made.id == "abc123"
    assert made.key.get_secret_value() == "sk-or-v1-1234567890"


def test_a_created_key_without_a_hash_has_an_empty_id() -> None:
    made = run_key_made(201, {"key": "sk-or-v1-1234567890"})
    assert made is not None
    assert made.id == ""


def test_a_refusal_whose_body_reads_like_a_key_makes_nothing() -> None:
    assert run_key_made(403, {"key": "refused-key", "error": "no"}) is None
    assert run_key_made(500, {"key": "refused-key"}) is None


def test_a_key_shorter_than_eight_characters_makes_nothing() -> None:
    assert run_key_made(201, {"key": "1234567"}) is None
    assert run_key_made(201, {"key": "12345678"}) is not None


def test_a_body_that_is_not_an_object_or_has_no_string_key_makes_nothing() -> None:
    assert run_key_made(201, ["key"]) is None
    assert run_key_made(201, {"key": 12345678901}) is None
    assert run_key_made(201, {"data": {"hash": 5}, "key": "12345678"}) is not None
