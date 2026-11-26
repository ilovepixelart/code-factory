"""A running run's progress from its own log. The logs are the shapes claude and codex record
(the previous implementation's `run_progress.rs` cases for those two, counted by hand there);
the other runtimes' records are not read."""

import json
from collections.abc import Sequence

import pytest

from code_factory.agents.models.progress import ChangedFiles, RunProgress, ToolCounts
from code_factory.agents.rules.progress import NAMED_FILES, changed_files, run_progress, tool_counts

CLAUDE = """not json at all
{"type":"system","subtype":"init","session_id":"s"}
{"type":"assistant","message":{"id":"m1","role":"assistant","content":[{"type":"thinking","thinking":"x"}],"usage":{"input_tokens":10,"output_tokens":0}}}
{"type":"assistant","message":{"id":"m1","role":"assistant","content":[{"type":"tool_use","id":"t1","name":"Read","input":{"file_path":"a.rs"}}],"usage":{"input_tokens":10,"output_tokens":1}}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t1","content":"x"}]}}
{"type":"assistant","message":{"id":"m2","role":"assistant","content":[{"type":"tool_use","id":"t2","name":"Edit","input":{"file_path":"a.rs"}},{"type":"tool_use","id":"t3","name":"Bash","input":{"command":"ls"}}],"usage":{"input_tokens":20,"output_tokens":2}}}
{"type":"assistant","message":{"id":"m3","role":"assistant","content":[{"type":"text","text":"x"}],"usage":{"input_tokens":30,"output_tokens":3}}}
""".strip().split("\n")

CODEX = """{"type":"thread.started","thread_id":"t"}
{"type":"turn.started"}
{"type":"item.started","item":{"id":"i0","type":"command_execution","command":"ls","status":"in_progress"}}
{"type":"item.completed","item":{"id":"i0","type":"command_execution","command":"ls","status":"completed"}}
{"type":"item.completed","item":{"id":"i1","type":"reasoning","text":"x"}}
{"type":"item.completed","item":{"id":"i2","type":"file_change","changes":[{"path":"a","kind":"update"}],"status":"completed"}}
{"type":"item.completed","item":{"id":"i3","type":"mcp_tool_call","server":"s","tool":"t","status":"completed"}}
{"type":"item.completed","item":{"id":"i4","type":"agent_message","text":"done"}}
{"type":"item.completed","item":{"id":"i5","type":"todo_list","items":[]}}
""".strip().split("\n")


def counts(lines: Sequence[str]) -> tuple[int, int, int] | None:
    found = tool_counts(lines)
    return None if found is None else (found.calls, found.reads, found.changes)


def test_a_claude_log_counts_one_read_one_edit_and_one_shell_command() -> None:
    assert counts(CLAUDE) == (3, 1, 1)


def test_a_codex_log_counts_a_command_an_mcp_call_and_a_file_change() -> None:
    assert counts(CODEX) == (3, 0, 1)


def test_a_known_shape_with_no_tool_call_yet_is_zero_not_unknown() -> None:
    assert counts(['{"type":"system"}']) == (0, 0, 0)
    assert counts(['{"type":"thread.started"}']) == (0, 0, 0)


@pytest.mark.parametrize(
    "log",
    [
        [],
        [""],
        ["just some text"],
        ['{"kind":"other"}'],
        ['{"type":"agent_start"}'],
        ['{"type":"assistant","message":{"content":"a word"}}'],
        ['{"type":"assistant","message":{"content":[{"type":"tool_use"}]}}'],
        ['{"type":"item.completed","item":{}}'],
        ['{"type":"item.completed"}'],
        ['{"type":"message_end","message":{"role":"assistant","content":[]}}'],
    ],
)
def test_a_log_of_no_known_shape_or_a_tool_record_that_cannot_be_read_gives_none(
    log: list[str],
) -> None:
    assert tool_counts(log) is None


def test_a_record_that_cannot_be_read_voids_the_counts_even_after_good_ones() -> None:
    assert tool_counts([*CLAUDE, '{"type":"assistant","message":{"content":"w"}}']) is None


@pytest.mark.parametrize("name", ["Read", "Grep", "Glob", "LS", "list", "FIND", "Search"])
def test_these_tools_are_reads(name: str) -> None:
    line = json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name}]}}
    )
    assert counts([line]) == (1, 1, 0)


@pytest.mark.parametrize(
    "name", ["Edit", "MultiEdit", "write", "NotebookEdit", "patch", "apply_patch"]
)
def test_these_tools_are_changes(name: str) -> None:
    line = json.dumps(
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name}]}}
    )
    assert counts([line]) == (1, 0, 1)


def call(call_id: str, name: str, **arguments: str) -> str:
    block = {"type": "tool_use", "id": call_id, "name": name, "input": arguments}
    return json.dumps({"type": "assistant", "message": {"content": [block]}})


def result(call_id: str, *, error: bool) -> str:
    block = {"type": "tool_result", "tool_use_id": call_id, "is_error": error, "content": "x"}
    return json.dumps({"type": "user", "message": {"content": [block]}})


def test_a_write_the_tool_refused_was_called_and_changed_nothing() -> None:
    log = [
        call("c1", "Write", path="a"),
        call("c2", "Write", path="b"),
        result("c1", error=True),
        result("c2", error=False),
    ]
    assert counts(log) == (2, 0, 1)


def test_a_refused_read_or_command_changes_no_count() -> None:
    log = [
        call("c1", "Read"),
        call("c2", "Bash"),
        result("c1", error=True),
        result("c2", error=True),
    ]
    assert counts(log) == (2, 1, 0)


def test_a_refused_change_is_taken_back_once_whatever_the_order_of_records() -> None:
    log = [call("c1", "Edit"), result("c1", error=True), result("c1", error=True)]
    assert counts(log) == (1, 0, 0)


def test_a_failed_codex_file_change_is_a_call_and_no_change() -> None:
    failed = '{"type":"item.completed","item":{"id":"i","type":"file_change","status":"failed"}}'
    assert counts([failed]) == (1, 0, 0)


def test_the_same_call_in_a_row_is_counted_as_repeated_and_the_last_tool_is_named() -> None:
    same = [call("a", "Bash", command="ls"), call("b", "Bash", command="ls")]
    assert tool_counts(same) == ToolCounts(
        calls=2, reads=0, changes=0, repeated=2, last_tool="Bash"
    )
    other = [*same, call("c", "Bash", command="pwd")]
    assert tool_counts(other) == ToolCounts(calls=3, repeated=1, last_tool="Bash")
    again = [*other, call("d", "Read", file_path="x")]
    assert tool_counts(again) == ToolCounts(calls=4, reads=1, repeated=1, last_tool="Read")
    assert tool_counts(['{"type":"system"}']) == ToolCounts()


def progress(
    lines: Sequence[str] | None, reported: int | None = None, last: float | None = None
) -> RunProgress:
    return run_progress(lines, reported, None, last)


def test_the_tokens_so_far_are_each_messages_last_usage_added() -> None:
    log = [
        '{"type":"assistant","message":{"id":"m1","content":[],"usage":{"input_tokens":10,"output_tokens":0}}}',
        '{"type":"assistant","message":{"id":"m1","content":[],"usage":{"input_tokens":10,"output_tokens":1}}}',
        '{"type":"assistant","message":{"id":"m2","content":[],"usage":{"input_tokens":20,"output_tokens":2}}}',
    ]
    assert progress(log).tokens == 33


def test_a_result_records_usage_is_the_tokens_of_a_finished_run() -> None:
    log = ['{"type":"result","usage":{"input_tokens":900,"output_tokens":100}}', *CLAUDE]
    assert progress(log).tokens == 1000


def test_a_report_to_the_board_beats_a_smaller_log_and_a_smaller_one_does_not() -> None:
    log = CLAUDE
    assert progress(log).tokens == 66
    assert progress(log, 1000).tokens == 1000
    assert progress(log, 5).tokens == 66


def test_an_empty_report_over_a_log_that_cannot_tell_is_no_tokens_not_zero() -> None:
    assert progress(["plain text"], 0).tokens is None
    assert progress(["plain text"], None).tokens is None
    assert progress(["plain text"], 7).tokens == 7


def test_codex_turns_give_the_input_less_its_cached_part_and_the_output() -> None:
    log = [
        '{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":5}}'
    ]
    assert progress(log).tokens == 65


def test_a_log_that_cannot_be_read_gives_no_counts_and_no_activity() -> None:
    nothing = run_progress(None, None, None, None)
    assert nothing == RunProgress()
    assert nothing.tool_calls is None


def test_the_progress_carries_the_counts_the_files_and_the_logs_last_growth() -> None:
    files = ChangedFiles(count=1, names=("a.py",))
    got = run_progress(CLAUDE, None, files, 1_790_000_123.0)
    assert got == RunProgress(
        tool_calls=3, reads=1, changes=1, files=files, tokens=66, last_activity=1_790_000_123.0
    )


def test_changed_files_name_ten_in_name_order_and_count_all() -> None:
    names = [f"new{n:02d}.txt" for n in range(12)]
    found = changed_files(["z.txt", "b.txt"], ["a.txt", "b.txt", "", *names])
    assert found == ChangedFiles(
        count=15,
        names=(
            "a.txt",
            "b.txt",
            "new00.txt",
            "new01.txt",
            "new02.txt",
            "new03.txt",
            "new04.txt",
            "new05.txt",
            "new06.txt",
            "new07.txt",
        ),
    )
    assert NAMED_FILES == 10
    assert changed_files([], []) == ChangedFiles(count=0, names=())
