import json
from typing import Any

import pytest

from code_factory.sessions.rules import capture
from sessions_values import NOW, golden

CASES = list(zip(golden("capture_cases.json"), golden("capture_cases.golden.json"), strict=True))


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_a_payload_becomes_the_spool_line_the_previous_hook_wrote(
    raw: str, expected: dict[str, str]
) -> None:
    result = capture.record(raw.encode(), NOW)
    if "refused" in expected:
        assert isinstance(result, capture.Refused)
        assert result.reason.startswith(expected["refused"] + ":")
    else:
        assert result == capture.Record(expected["spool"], expected["line"])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"token": "abc123"}', '{"token": "[redacted]"}'),
        ("Authorization: Bearer abc.def ghi", "Authorization: [redacted] ghi"),
        ("api_key=sk-12345", "api_key=[redacted]"),
        ("ghp_abcDEF123", "[redacted]"),
        ("password = 'two words' next", "password = '[redacted]' next"),
        ("AKIAABCDEFGHIJKLMNOP", "[redacted]"),
        ("AKIAABCDEFGHIJKLMNO", "AKIAABCDEFGHIJKLMNO"),
        ("AKIAABCDEFGHIJKLMNOPQ", "AKIAABCDEFGHIJKLMNOPQ"),
        ("nothing secret here", "nothing secret here"),
    ],
)
def test_mask_keeps_the_key_and_replaces_the_value(text: str, expected: str) -> None:
    assert capture.mask(text) == expected


def test_a_string_of_2000_characters_is_kept_and_2001_is_trimmed() -> None:
    kept = capture.record(json.dumps({"session_id": "s", "t": "x" * 2000}).encode(), NOW)
    trimmed = capture.record(json.dumps({"session_id": "s", "t": "x" * 2001}).encode(), NOW)
    assert isinstance(kept, capture.Record)
    assert isinstance(trimmed, capture.Record)
    assert json.loads(kept.line)["t"] == "x" * 2000
    assert json.loads(trimmed.line)["t"] == {"_trimmed_chars": 2001, "head": "x" * 200}


def test_strings_inside_lists_and_objects_are_trimmed_too() -> None:
    raw = json.dumps({"session_id": "s", "a": [{"b": ["é" * 2001]}]}).encode()
    result = capture.record(raw, NOW)
    assert isinstance(result, capture.Record)
    assert json.loads(result.line)["a"] == [{"b": [{"_trimmed_chars": 2001, "head": "é" * 200}]}]


def test_a_secret_is_masked_before_the_length_is_measured() -> None:
    raw = json.dumps({"session_id": "s", "t": "password=" + "y" * 5000}).encode()
    result = capture.record(raw, NOW)
    assert isinstance(result, capture.Record)
    assert json.loads(result.line)["t"] == "password=[redacted]"


@pytest.mark.parametrize("number", ["NaN", "Infinity", "1e999"])
def test_not_a_number_is_refused_because_the_ledger_cannot_store_it(number: str) -> None:
    result = capture.record(b'{"session_id": "s", "x": ' + number.encode() + b"}", NOW)
    assert isinstance(result, capture.Refused)
    assert result.reason.startswith("ValueError:")


def test_apply_redaction_replaces_each_find_in_the_order_given() -> None:
    patterns = [("secret plan", "[ctx]"), ("plan", "[short]")]
    assert capture.apply_redaction("a secret plan and a plan", patterns) == "a [ctx] and a [short]"
    assert capture.apply_redaction(b"a secret plan", patterns) == b"a [ctx]"


def test_a_prompt_has_the_owner_context_replaced_by_its_placeholder() -> None:
    context = "Always answer in rhyme."
    raw = json.dumps({"session_id": "s", "prompt": f"Do it.\n{context}"}).encode()
    result = capture.record(raw, NOW, [(context, "[owner context for a, 23 characters]")])
    assert isinstance(result, capture.Record)
    assert json.loads(result.line)["prompt"] == "Do it.\n[owner context for a, 23 characters]"


def test_a_context_written_with_unicode_escapes_is_replaced() -> None:
    raw = b'{"session_id": "s", "prompt": "caf\\u00e9 rules"}'
    result = capture.record(raw, NOW, [("café rules", "[ctx]")])
    assert isinstance(result, capture.Record)
    assert json.loads(result.line)["prompt"] == "[ctx]"


def test_text_that_only_looks_like_a_fence_is_not_redacted() -> None:
    planted = "BEGIN OWNER CONTEXT x FOR a\nnot the context\nEND OWNER CONTEXT x FOR a"
    raw = json.dumps({"session_id": "s", "prompt": planted}).encode()
    result = capture.record(raw, NOW, [("the real context", "[ctx]")])
    assert isinstance(result, capture.Record)
    assert json.loads(result.line)["prompt"] == planted


def test_a_failure_entry_names_the_reason_and_the_first_200_bytes() -> None:
    entry = capture.failure_entry("JSONDecodeError: boom", b"x" * 300, 5.0)
    assert entry == (
        json.dumps({"at": 5.0, "reason": "JSONDecodeError: boom", "payload_head": "x" * 200}) + "\n"
    )


def recorded(payload: dict[str, object]) -> dict[str, Any]:
    result = capture.record(json.dumps({"session_id": "s", **payload}).encode(), NOW)
    assert isinstance(result, capture.Record)
    return json.loads(result.line)


def test_a_string_under_a_secret_key_is_redacted_whatever_the_value_looks_like() -> None:
    found = recorded(
        {
            "tool_input": {"password": "hunter2", "api_key": "k", "note": "plain"},
            "headers": {"Authorization": "Bearer abc", "x-api-key": "k2", "github_token": "t"},
            "list": [{"secret": "s"}],
        }
    )
    assert found["tool_input"] == {
        "password": "[redacted]",
        "api_key": "[redacted]",
        "note": "plain",
    }
    assert found["headers"] == {
        "Authorization": "[redacted]",
        "x-api-key": "[redacted]",
        "github_token": "[redacted]",
    }
    assert found["list"] == [{"secret": "[redacted]"}]


def test_keys_that_only_contain_a_secret_word_and_non_string_values_are_kept() -> None:
    found = recorded(
        {
            "usage": {"input_tokens": "12", "max_tokens": 5, "token": 7, "secret_santa": "x"},
            "passwordless": "yes",
        }
    )
    assert found["usage"] == {
        "input_tokens": "12",
        "max_tokens": 5,
        "token": 7,
        "secret_santa": "x",
    }
    assert found["passwordless"] == "yes"


def test_a_long_secret_under_a_secret_key_is_redacted_not_trimmed() -> None:
    found = recorded({"password": "x" * 5000})  # a test value
    assert found["password"] == "[redacted]"  # noqa: S105  # the mask, not a secret


GATE = "gate: pytest failed (exit 1)"


def test_a_trimmed_tool_output_keeps_the_gate_failure_lines_it_held() -> None:
    long = "noise\n" * 500 + f"{GATE}\n  gate: ruff failed (exit 2)  \nnote: {GATE} inside words\n"
    found = recorded({"tool_response": {"stdout": long}})
    stdout = found["tool_response"]["stdout"]
    assert stdout["_trimmed_chars"] == len(long)
    assert stdout["gates"] == [GATE, "gate: ruff failed (exit 2)"]
    assert list(stdout) == ["_trimmed_chars", "head", "gates"]


def test_a_trimmed_string_without_gate_lines_has_the_two_keys_it_always_had() -> None:
    found = recorded({"text": "noise\n" * 500})
    assert list(found["text"]) == ["_trimmed_chars", "head"]
