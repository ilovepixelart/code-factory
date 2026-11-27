import random
import time

import pytest

from code_factory.sessions.models import Event
from code_factory.sessions.rules import timeline as rules
from sessions_values import answer, events_by_session, golden, sample_events

TIMELINE_IDS = [
    item["path"].split("/")[3]
    for item in golden("answers.json")
    if item["path"].endswith("/timeline") and item["status"] == 200
]


@pytest.mark.parametrize("session_id", TIMELINE_IDS)
def test_a_sample_sessions_timeline_is_what_the_previous_answer_listed(session_id: str) -> None:
    expected = answer(f"/api/sessions/{session_id}/timeline")["body"]
    entries = rules.timeline(events_by_session(sample_events())[session_id])
    shown, earlier = rules.window(entries, 500)
    assert [rules.entry_json(entry) for entry in shown] == expected["entries"]
    assert (len(entries), earlier) == (expected["total"], expected["earlier_prompts"])


def event(seq: int, name: str, agent: str | None = None, **payload: object) -> Event:
    return Event(seq, "s", agent, name, float(seq), "s.jsonl", seq, dict(payload))


def call(seq: int, tool_id: str, agent: str | None = None, tool: str = "Bash") -> Event:
    return event(seq, "PreToolUse", agent, tool_name=tool, tool_use_id=tool_id)


@pytest.mark.parametrize(
    ("events", "status"),
    [
        ([call(1, "a"), event(2, "PostToolUse", tool_use_id="a")], "done"),
        ([call(1, "a"), event(2, "PostToolUseFailure", tool_use_id="a")], "failed"),
        ([call(1, "a")], "running"),
        ([call(1, "a"), event(2, "PermissionRequest", tool_name="Bash")], "waiting"),
        ([call(1, "a"), event(2, "Stop")], "interrupted"),
        (
            [call(1, "a"), event(2, "PermissionRequest", tool_name="Bash"), event(3, "Stop")],
            "denied",
        ),
        (
            [call(1, "a"), event(2, "PermissionRequest", tool_name="Edit"), event(3, "Stop")],
            "interrupted",
        ),
        ([call(1, "a"), event(2, "Stop"), event(3, "PostToolUse", tool_use_id="a")], "interrupted"),
        ([call(1, "a", "x"), event(2, "SubagentStop", "x")], "interrupted"),
        (
            [call(1, "a", "x"), event(2, "Stop"), event(3, "PostToolUse", "x", tool_use_id="a")],
            "done",
        ),
        ([call(1, "a"), event(2, "PostToolUse", "x", tool_use_id="a")], "running"),
    ],
    ids=[
        "done",
        "failed",
        "running",
        "waiting",
        "interrupted",
        "denied",
        "other tool asked",
        "result after the turn closed",
        "subagent stopped",
        "main stop leaves a subagent",
        "another agent's result",
    ],
)
def test_a_tool_call_has_the_outcome_its_later_events_of_the_same_agent_give(
    events: list[Event], status: str
) -> None:
    assert rules.timeline(events)[0].status == status


def test_a_result_with_a_duration_reports_it_and_one_without_the_gap() -> None:
    timed = [call(1, "a"), event(5, "PostToolUse", tool_use_id="a", duration_ms=250)]
    gap = [call(1, "a"), event(5, "PostToolUse", tool_use_id="a")]
    assert rules.timeline(timed)[0].duration_seconds == 0.25
    assert rules.timeline(gap)[0].duration_seconds == 4.0


def random_events(seed: int, size: int) -> list[Event]:
    rng = random.Random(seed)  # noqa: S311  # a reproducible test sequence
    names = ["PreToolUse"] * 5 + ["PostToolUse", "PostToolUseFailure", "PermissionRequest"]
    names += ["Stop", "UserPromptSubmit", "SubagentStop", "Notification"]
    found = []
    for seq in range(1, size + 1):
        name = rng.choice(names)
        found.append(
            event(
                seq,
                name,
                rng.choice([None, None, "x", "y"]),
                tool_name=rng.choice(["Bash", "Edit"]),
                tool_use_id=rng.choice(["a", "b", "c", None]),
            )
        )
    return found


@pytest.mark.parametrize("seed", range(40))
def test_the_one_pass_timeline_agrees_with_the_naive_scan_of_each_call(seed: int) -> None:
    events = random_events(seed, 40)
    fast = rules.timeline(events)
    tools = [entry for entry in fast if entry.kind == "tool"]
    scanned = [
        rules.outcome_of(events, at)[1] for at, e in enumerate(events) if e.name == "PreToolUse"
    ]
    assert [entry.status for entry in tools] == scanned


def test_a_long_turns_timeline_is_built_in_linear_time() -> None:
    events = []
    for n in range(2500):
        events.append(call(2 * n + 1, f"t{n}"))
        events.append(event(2 * n + 2, "PostToolUse", tool_use_id=f"t{n}"))
    started = time.perf_counter()
    entries = rules.timeline(events)
    assert time.perf_counter() - started < 0.1
    assert len(entries) == 2500


def test_a_window_keeps_the_last_entries_and_counts_the_earlier_prompts() -> None:
    events = [
        event(1, "UserPromptSubmit", prompt="one"),
        call(2, "a"),
        event(3, "UserPromptSubmit", prompt="two"),
        call(4, "b"),
        call(5, "c"),
    ]
    entries = rules.timeline(events)
    shown, earlier = rules.window(entries, 2)
    assert ([entry.seq for entry in shown], earlier) == ([4, 5], 2)
    shown, earlier = rules.window(entries, 5)
    assert ([entry.seq for entry in shown], earlier) == ([1, 2, 3, 4, 5], 0)


def test_a_call_has_its_input_and_the_output_its_result_carried() -> None:
    events = [
        event(1, "PreToolUse", tool_name="Bash", tool_use_id="a", tool_input={"command": "ls"}),
        event(2, "PostToolUse", tool_use_id="a", tool_response={"stdout": "x"}),
        event(3, "PreToolUse", tool_name="Edit", tool_use_id="b", tool_input={"file_path": "f"}),
        event(4, "PostToolUseFailure", tool_use_id="b", error="denied"),
        event(5, "PreToolUse", tool_name="Read", tool_use_id="c"),
    ]
    assert rules.tool_call(events, 1) == rules.ToolCall("Bash", {"command": "ls"}, {"stdout": "x"})
    assert rules.tool_call(events, 3) == rules.ToolCall("Edit", {"file_path": "f"}, "denied")
    assert rules.tool_call(events, 5) == rules.ToolCall("Read", None, None)


def test_no_call_has_a_seq_that_is_not_a_tool_call() -> None:
    events = [call(1, "a"), event(2, "Stop")]
    assert rules.tool_call(events, 2) is None
    assert rules.tool_call(events, 9) is None
