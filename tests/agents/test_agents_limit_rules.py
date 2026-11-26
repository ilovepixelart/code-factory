"""A run that ended on its runtime's usage limit, read from its log, and when a codex limit
resets. The shapes are claude's `result` and `rate_limit_event` records and codex's `exec` event
types (`turn.failed` with `error.message`, `error` with `message`)."""

import json
from typing import Any

import pytest

from code_factory.agents.models.usage import Limit
from code_factory.agents.rules.limits import codex_reset, usage_limit


def lines(*records: dict[str, Any]) -> str:
    return "".join(json.dumps(record) + "\n" for record in records)


def claude(text: str, *, is_error: bool) -> dict[str, Any]:
    return {"type": "result", "subtype": "success", "is_error": is_error, "result": text}


def codex(kind: str, message: str) -> dict[str, Any]:
    if kind == "turn.failed":
        return {"type": kind, "error": {"message": message}}
    return {"type": kind, "message": message}


STARTED = ({"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"})


@pytest.mark.parametrize(
    "text",
    [
        "You've hit your session limit · resets 3pm",
        "You've reached your weekly limit",
        "usage limit reached",
        "You are out of usage",
        "Quota exceeded",
        "You exceeded your current quota",
        "insufficient_quota",
    ],
)
def test_a_claude_error_result_in_a_limits_words_is_a_usage_limit(text: str) -> None:
    assert usage_limit(lines(claude(text, is_error=True))) == Limit(reset=None)


def test_a_result_that_is_no_error_or_not_in_a_limits_words_is_no_limit() -> None:
    for log in (
        lines(claude("I stopped before the usage limit", is_error=False)),
        lines(claude("API Error: 529 overloaded", is_error=True)),
        "plain text, no records\n",
        "",
    ):
        assert usage_limit(log) is None, log


def event(status: str, at: int) -> dict[str, Any]:
    return {"type": "rate_limit_event", "rate_limit_info": {"status": status, "resetsAt": at}}


def test_the_reset_is_the_last_rejected_rate_limit_events() -> None:
    stream = lines(
        event("rejected", 1_790_000_900),
        event("rejected", 1_790_007_200),
        event("allowed", 1_790_000_100),
        claude("You've hit your session limit · resets 3pm", is_error=True),
    )
    assert usage_limit(stream) == Limit(reset=1_790_007_200.0)


def test_a_limit_with_no_rejected_event_has_no_reset() -> None:
    stream = lines(
        event("allowed", 1_790_000_100),
        claude("You've hit your weekly limit · resets Oct 9, 3pm", is_error=True),
    )
    assert usage_limit(stream) == Limit(reset=None)


@pytest.mark.parametrize("kind", ["turn.failed", "error"])
def test_a_codex_failure_in_a_limits_words_is_a_limit_with_no_reset(kind: str) -> None:
    log = lines(*STARTED, codex(kind, "You've hit your usage limit."))
    assert usage_limit(log) == Limit(reset=None)


@pytest.mark.parametrize(
    "failure",
    [
        codex("turn.failed", "stream disconnected before completion"),
        codex("error", "exec command rejected by user"),
        {"type": "item.completed", "item": {"type": "agent_message", "text": "the usage limit"}},
        {"type": "turn.started", "message": "usage limit"},
    ],
)
def test_a_codex_failure_in_other_words_or_a_limits_words_in_another_record_is_no_limit(
    failure: dict[str, Any],
) -> None:
    assert usage_limit(lines(*STARTED, failure)) is None


def test_the_last_codex_failure_decides() -> None:
    log = lines(
        *STARTED,
        codex("turn.failed", "You've hit your usage limit."),
        *STARTED,
        codex("turn.failed", "stream disconnected before completion"),
    )
    assert usage_limit(log) is None
    flipped = lines(
        *STARTED,
        codex("turn.failed", "stream disconnected before completion"),
        codex("error", "Quota exceeded"),
    )
    assert usage_limit(flipped) == Limit(reset=None)


def test_a_codex_limit_error_the_run_got_past_is_no_limit_but_a_later_one_is() -> None:
    recovered = lines(
        *STARTED,
        codex("error", "Quota exceeded. Reconnecting..."),
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
    )
    assert usage_limit(recovered) is None
    again = lines(
        *STARTED,
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
        *STARTED,
        codex("turn.failed", "You've hit your usage limit."),
    )
    assert usage_limit(again) == Limit(reset=None)


def window(used: float, resets: int | None) -> dict[str, Any]:
    return {"usedPercent": used, "windowDurationMins": 300, "resetsAt": resets}


def limits(primary: object, secondary: object) -> str:
    return json.dumps(
        {
            "id": 2,
            "result": {
                "ordinaryUsageAllowed": True,
                "rateLimits": {"limitId": "codex", "primary": primary, "secondary": secondary},
            },
        }
    )


def test_a_codex_limit_resets_at_the_earliest_full_window() -> None:
    both = limits(window(100, 1_795_000_900), window(100, 1_795_000_300))
    one_full = limits(window(40, 1_795_000_100), window(100, 1_795_000_300))
    over = limits(window(130, 1_795_000_500), None)
    assert codex_reset(both) == 1_795_000_300.0
    assert codex_reset(one_full) == 1_795_000_300.0
    assert codex_reset(over) == 1_795_000_500.0


def test_no_full_window_a_full_one_without_a_reset_or_no_answer_gives_none() -> None:
    answers = [
        limits(window(99, 1_795_000_300), None),
        limits(window(99.9, 1_795_000_300), None),
        limits(window(100, None), None),
        limits(None, None),
        json.dumps({"id": 2, "error": {"code": -32601, "message": "no"}}),
        json.dumps({"id": 2, "result": {}}),
        "not json",
        "[1]",
    ]
    assert [codex_reset(answer) for answer in answers] == [None] * len(answers)
