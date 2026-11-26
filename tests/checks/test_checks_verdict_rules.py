"""The commit status, the judged exit, the sleep excuse, the ledger record and the kill policy."""

from typing import Any

import pytest

from code_factory.checks.models import Judged, Ran
from code_factory.checks.rules import (
    checks_record,
    clean_log_tail,
    judged_exit,
    kill_policy,
    slept_between,
    status_for,
    verdict_for,
)
from code_factory.stages.models import LogReading

COMMIT = "a" * 40


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"commit": COMMIT, "exit_code": 0}, ("success", "The board's checks passed")),
        (
            {"commit": COMMIT, "exit_code": 3},
            ("failure", "The board's checks failed: exited 3"),
        ),
        (
            {"commit": COMMIT},
            ("failure", "The board's checks failed: did not run"),
        ),
        (
            {"commit": COMMIT, "exit_code": -1, "reason": "checks container unavailable"},
            ("pending", "The checks container could not start"),
        ),
        (
            {"commit": COMMIT, "exit_code": -1},
            ("pending", "The board's checks gave no verdict and run again"),
        ),
        (
            {"commit": COMMIT, "exit_code": 137},
            ("pending", "The board's checks gave no verdict and run again"),
        ),
        (
            {"commit": COMMIT, "exit_code": 137, "reason": "checks container unavailable"},
            ("pending", "The checks container could not start"),
        ),
    ],
)
def test_a_record_becomes_the_status_the_forge_shows(
    record: dict[str, Any], expected: tuple[str, str]
) -> None:
    assert status_for(record) == expected


def test_a_container_reason_on_a_real_failure_is_still_a_failure() -> None:
    record = {"commit": COMMIT, "exit_code": 2, "reason": "checks container unavailable"}
    assert status_for(record) == ("failure", "The board's checks failed: exited 2")


def test_a_record_without_a_commit_posts_no_status() -> None:
    assert status_for({"exit_code": 0}) is None
    assert status_for({"commit": "", "exit_code": 0}) is None


def _judged(head: str = "h1", tree: str = "t1", tree_id: str = "i1", tracked: str = "k1") -> Judged:
    return Judged(head=head, tree=tree, tree_id=tree_id, tracked=tracked)


def test_the_code_stands_while_the_tree_holds() -> None:
    assert judged_exit(_judged(), _judged(), 3) == (3, False)


@pytest.mark.parametrize(
    "after", [_judged(head="h2"), _judged(tracked="k2"), _judged(tree_id="i2")]
)
def test_a_tree_that_moved_gives_no_verdict(after: Judged) -> None:
    assert judged_exit(_judged(), after, 0) == (-1, True)


def test_a_new_untracked_file_alone_keeps_the_verdict() -> None:
    assert judged_exit(_judged(), _judged(tree="t2"), 0) == (0, False)


@pytest.mark.parametrize(
    ("before", "after", "code", "expected"),
    [
        ("100", "200", 1, True),  # failed, and the machine slept meanwhile
        ("100", "100", 1, False),  # failed, no sleep
        ("100", "200", 0, False),  # passed: nothing to excuse
        (None, "200", 1, False),  # no first reading
        ("100", None, 1, False),  # no second reading
    ],
)
def test_a_failure_is_excused_only_when_the_sleep_time_changed(
    before: str | None, after: str | None, code: int, expected: bool
) -> None:
    assert slept_between(before, after, code) is expected


def _reading(**fields: object) -> LogReading:
    return LogReading.model_validate(fields)


def test_a_passed_record_has_the_four_keys_and_the_tree_id() -> None:
    record = checks_record(Judged(head=COMMIT, tree="t", tree_id="i"), 0, "/s/a.log", _reading())
    assert record == {
        "commit": COMMIT,
        "exit_code": 0,
        "log": "/s/a.log",
        "tree": "t",
        "tree_id": "i",
    }


def test_an_empty_tree_id_is_left_out() -> None:
    record = checks_record(Judged(head=COMMIT, tree="t"), 0, "/s/a.log", _reading())
    assert "tree_id" not in record


def test_a_failure_carries_the_reading_of_its_log() -> None:
    reading = _reading(
        failure_reason="build failed",
        flaky_steps=["rust-test"],
        reported_steps=[("preflight", "passed"), ("rust-test", "failed")],
        step_seconds=[("preflight", 3)],
        lock_waits=[("rust-test", 20)],
        quarantined_failures=[("suite::slow", 2)],
    )
    record = checks_record(
        Judged(head=COMMIT, tree="t"), 101, "/s/a.log", reading, slept=True, extra={"step": "x"}
    )
    assert record == {
        "commit": COMMIT,
        "exit_code": 101,
        "log": "/s/a.log",
        "tree": "t",
        "slept": True,
        "reason": "build failed",
        "retried": ["rust-test"],
        "steps": {"preflight": "passed", "rust-test": "failed"},
        "seconds": {"preflight": 3},
        "lock_waits": {"rust-test": 20},
        "quarantined": {"suite::slow": 2},
        "step": "x",
    }


def test_a_container_that_never_started_is_named_for_a_run_without_a_verdict() -> None:
    log = "docker: Error\ngate: the checks container could not start: no verdict\n"
    record = checks_record(Judged(head=COMMIT, tree="t"), -1, "/s/a.log", _reading(), text=log)
    assert record["reason"] == "checks container unavailable"


def test_the_container_line_names_nothing_for_another_code() -> None:
    log = "gate: the checks container could not start: no verdict\n"
    record = checks_record(Judged(head=COMMIT, tree="t"), 2, "/s/a.log", _reading(), text=log)
    assert "reason" not in record


def test_a_log_that_could_not_be_read_marks_the_record() -> None:
    record = checks_record(Judged(head=COMMIT, tree="t"), 0, "/s/a.log", None)
    assert record["log_unread"] is True


def _ran(code: int, *, killed: bool, step: str | None = None, log: str = "/s/a.log") -> Ran:
    return Ran(code=code, log=log, killed=killed, step=step)


def test_a_run_that_was_not_killed_is_final_with_no_kills() -> None:
    action = kill_policy([_ran(1, killed=False)])
    assert (action.rerun, action.record_kill, action.kills) == (False, None, [])


def test_the_first_kill_is_recorded_with_its_step_and_run_again() -> None:
    action = kill_policy([_ran(137, killed=True, step="rust-test")])
    assert action.rerun is True
    assert action.record_kill == {"outcome": "killed", "step": "rust-test"}


def test_a_second_kill_ends_with_both_in_the_final_record() -> None:
    first = _ran(137, killed=True, step="a", log="/s/1.log")
    second = _ran(143, killed=True, step="b", log="/s/2.log")
    action = kill_policy([first, second])
    assert action.rerun is False
    assert action.kills == [
        {"step": "a", "log": "/s/1.log", "exit_code": 137},
        {"step": "b", "log": "/s/2.log", "exit_code": 143},
    ]


def test_a_kill_then_a_clean_run_leaves_no_kills_in_the_final_record() -> None:
    action = kill_policy([_ran(137, killed=True, step="a"), _ran(0, killed=False)])
    assert (action.rerun, action.kills) == (False, [])


def _record(commit: str, code: int | None, tree_id: str = "T", **extra: object) -> dict[str, Any]:
    data: dict[str, Any] = {"commit": commit, "tree_id": tree_id, **extra}
    if code is not None:
        data["exit_code"] = code
    return data


def test_a_pass_on_the_trees_id_is_passed() -> None:
    assert verdict_for([_record("h", 0)], "h", "T") == "passed"


def test_a_pass_of_another_scope_does_not_stand_for_the_gates_command() -> None:
    fast = _record("h", 0, scope="fast")
    assert verdict_for([fast], "h", "T") == "missing"
    assert verdict_for([fast, _record("h", 2)], "h", "T") == "failed"
    assert verdict_for([_record("h", 0, scope="full")], "h", "T") == "missing"


def test_a_failure_on_the_trees_id_is_failed() -> None:
    assert verdict_for([_record("h", 2)], "h", "T") == "failed"


def test_a_pass_with_an_empty_or_another_tree_id_is_missing() -> None:
    assert verdict_for([_record("h", 0, tree_id="")], "h", "T") == "missing"
    assert verdict_for([_record("h", 0, tree_id="U")], "h", "T") == "missing"
    assert verdict_for([_record("h", 0)], "h", "") == "missing"


def test_no_verdict_codes_and_other_commits_and_kills_are_missing() -> None:
    assert verdict_for([_record("h", -1)], "h", "T") == "missing"
    assert verdict_for([_record("h", 137)], "h", "T") == "missing"
    assert verdict_for([_record("h", None)], "h", "T") == "missing"
    assert verdict_for([_record("other", 0)], "h", "T") == "missing"
    assert verdict_for([_record("h", 1, outcome="killed")], "h", "T") == "missing"
    assert verdict_for([], "h", "T") == "missing"


def test_the_newest_record_of_the_commit_decides() -> None:
    newest_first = [_record("h", 0), _record("h", 3)]
    assert verdict_for(newest_first, "h", "T") == "passed"
    assert verdict_for(list(reversed(newest_first)), "h", "T") == "failed"


def test_a_remote_log_tail_loses_its_control_characters_but_not_tabs_and_newlines() -> None:
    assert clean_log_tail("a\tb\nc\x1b[31md\x00e\r\n") == "a\tb\nc[31mde\n"
