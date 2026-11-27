import json

import pytest

from code_factory.sessions.models import NewEvent, Reject
from code_factory.sessions.rules import events


def row(line: bytes) -> NewEvent | Reject:
    return events.event_row("s.jsonl", 40, line)


def test_a_hook_payload_becomes_an_event_with_its_fields() -> None:
    line = (
        b'{"session_id":"s-1","agent_id":"a1","hook_event_name":"PreToolUse",'
        b'"tool_name":"Bash","_captured_at":1790000720.5}'
    )
    assert row(line) == NewEvent(
        "s.jsonl",
        40,
        "s-1",
        "a1",
        "PreToolUse",
        1790000720.5,
        {
            "session_id": "s-1",
            "agent_id": "a1",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "_captured_at": 1790000720.5,
        },
    )


def test_a_payload_with_no_session_agent_or_event_name_has_empty_ones() -> None:
    found = row(b'{"message":"no session","agent_id":null}')
    assert isinstance(found, NewEvent)
    assert (found.session_id, found.agent_id, found.event) == ("", None, "")


def test_a_number_as_session_id_is_its_text() -> None:
    found = row(b'{"session_id":5,"hook_event_name":"Stop"}')
    assert isinstance(found, NewEvent)
    assert found.session_id == "5"


@pytest.mark.parametrize(
    "stamp",
    [
        b"",
        b',"_captured_at":"x"',
        b',"_captured_at":1e300',
        b',"_captured_at":-5',
        b',"_captured_at":true',
    ],
    ids=["absent", "text", "huge", "negative", "bool"],
)
def test_a_captured_time_that_is_not_a_usable_number_is_the_epoch(stamp: bytes) -> None:
    found = row(b'{"session_id":"s"' + stamp + b"}")
    assert isinstance(found, NewEvent)
    assert found.captured_at == 0.0


@pytest.mark.parametrize(
    ("value", "kept"),
    [(b"0", 0.0), (b"253402300799", 253402300799.0), (b"253402300800", 0.0), (b"1.5", 1.5)],
)
def test_the_captured_time_range_is_zero_to_the_last_storable_second(
    value: bytes, kept: float
) -> None:
    found = row(b'{"session_id":"s","_captured_at":' + value + b"}")
    assert isinstance(found, NewEvent)
    assert found.captured_at == kept


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        (b"not json at all", "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"),
        (b"[1, 2, 3]", "not a JSON object"),
        (b"\xff\xfe", "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0"),
        (b'{"x": NaN}', "ValueError: NaN is not a number the ledger can store"),
        (b'{"x": 1e999}', "ValueError: 1e999 is not a number the ledger can store"),
        (b'{"x": [-Infinity]}', "ValueError: -Infinity is not a number the ledger can store"),
        (
            b'{"session_id": "a\\u0000b"}',
            "ValueError: a text field holds a NUL or a lone surrogate",
        ),
        (b'{"agent_id": "a\\ud800"}', "ValueError: a text field holds a NUL or a lone surrogate"),
        (
            b'{"hook_event_name": "x\\udfff"}',
            "ValueError: a text field holds a NUL or a lone surrogate",
        ),
    ],
)
def test_a_line_that_is_no_event_is_a_reject_that_names_why(line: bytes, reason: str) -> None:
    found = row(line)
    assert isinstance(found, Reject)
    assert found.reason.startswith(reason)
    assert (found.spool, found.offset) == ("s.jsonl", 40)


def test_a_reject_keeps_only_the_first_200_bytes_lossily_and_no_nul() -> None:
    found = row(b"\x00" + b"x" * 300 + b"\xff")
    assert isinstance(found, Reject)
    assert found.head == "\ufffd" + "x" * 199


def test_a_line_over_the_limit_is_rejected_with_its_head() -> None:
    assert events.too_long("s.jsonl", 9, b"abc") == Reject("s.jsonl", 9, "line too long", "abc")


def test_a_session_id_past_the_index_row_limit_is_a_reject_not_an_insert_error() -> None:
    too_big = "中" * 400  # 1,200 bytes
    found = row(json.dumps({"session_id": too_big, "hook_event_name": "Stop"}).encode())
    assert isinstance(found, Reject)
    assert found.reason == f"ValueError: {events.SESSION_ID_TOO_LONG}"


def test_a_session_id_at_the_byte_limit_is_kept() -> None:
    at_limit = "a" * events.MOST_SESSION_ID_BYTES
    found = row(json.dumps({"session_id": at_limit}).encode())
    assert isinstance(found, NewEvent)
    assert found.session_id == at_limit


def test_a_session_id_one_byte_past_the_limit_is_a_reject() -> None:
    over = "a" * (events.MOST_SESSION_ID_BYTES + 1)
    assert isinstance(row(json.dumps({"session_id": over}).encode()), Reject)
