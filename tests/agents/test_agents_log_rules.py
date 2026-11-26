"""Run log readers against the previous implementation's `costs.golden.json` (its claude cases;
the opencode one is not ported) and hand-worked codex turns."""

import json
from pathlib import Path

import pytest

from code_factory.agents.rules.logs import amount, log_usage, month_spent_note, spent_note

GOLDEN = json.loads(
    (Path(__file__).parent.parent / "golden" / "agents" / "costs.json").read_text(encoding="utf-8")
)
LOGS = {
    "claude": '{"type":"system"}\nnot json\n{"type":"result","total_cost_usd":0.12,'
    '"modelUsage":{"a":{"costUSD":0.02},"b":{"costUSD":0.1}}}\n',
    "claude-twice": '{"type":"result","total_cost_usd":1}\n'
    '{"type":"result","total_cost_usd":"0.5","modelUsage":{"only":null}}\n',
    "claude-negative": '{"type":"result","total_cost_usd":-1,"modelUsage":{}}\n',
    "nothing": "plain output\n",
    "empty": "",
    "missing": "",
}


@pytest.mark.parametrize("case", sorted(LOGS))
def test_the_cost_and_model_are_those_of_the_golden(case: str) -> None:
    usage = log_usage(LOGS[case].splitlines())
    assert {"cost": usage.cost, "model": usage.model} == GOLDEN[case]


def test_the_last_result_record_gives_the_tokens_and_a_log_of_no_known_shape_gives_none() -> None:
    log = [
        '{"type":"result","usage":{"input_tokens":10,"output_tokens":5,"cache_read_input_tokens":99}}'
    ]
    usage = log_usage(log)
    assert (usage.input_tokens, usage.output_tokens, usage.tokens) == (10, 5, 15)
    assert log_usage(["plain"]).tokens is None
    assert log_usage([]).cost is None


def test_codex_turns_add_their_input_less_the_cached_part_and_their_output() -> None:
    first = {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 7}
    second = {"input_tokens": 10, "cached_input_tokens": 30, "output_tokens": 1}
    log = [
        json.dumps({"type": "turn.completed", "usage": first}),
        json.dumps({"type": "turn.completed", "usage": second}),
        '{"type":"turn.started"}',
    ]
    usage = log_usage(log)
    assert (usage.input_tokens, usage.output_tokens) == (60, 8)


@pytest.mark.parametrize(
    ("value", "dollars"),
    [
        (0.5, 0.5),
        (1, 1.0),
        ("0.5", 0.5),
        (0, 0.0),
        (-1, None),
        ("x", None),
        (True, None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_an_amount_is_a_number_or_numeric_text_of_zero_or_more(
    value: object, dollars: float | None
) -> None:
    assert amount(value) == dollars


def test_the_budget_notes_show_both_amounts_to_the_cent() -> None:
    assert spent_note(4.5, 4.0) == "budget reached ($4.50 of $4.00)"
    assert month_spent_note("2026-11", 10, 9.5) == (
        "the repository's budget for 2026-11 is reached ($10.00 of $9.50)"
    )
