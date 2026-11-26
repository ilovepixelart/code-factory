"""When main's run is due, which step failed, the search for the merge, and a streak."""

from datetime import UTC, datetime, timedelta

import pytest

from code_factory.checks.models import MainRecord
from code_factory.checks.rules import (
    Bisection,
    bisect,
    blame_ticket,
    cause_before_any_step,
    complete_main,
    failed_step,
    first_parent_merges,
    main_due,
)

AT = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def run(  # the fields a record names
    commit: str,
    exit_code: int,
    *,
    passed: str = "",
    step: str = "",
    broken_by: str = "",
    searched: bool = False,
) -> MainRecord:
    return MainRecord(
        repository="sample",
        commit=commit,
        exit_code=exit_code,
        log="/s/l.log",
        at=AT,
        passed=passed,
        step=step,
        broken_by=broken_by,
        searched=searched,
    )


def test_a_run_is_due_on_a_tip_no_run_is_recorded_on() -> None:
    assert main_due(None, "aaa")
    assert main_due(run("aaa", 0), "bbb")
    assert main_due(run("aaa", 1), "bbb")


def test_the_tip_a_run_is_recorded_on_is_not_due_again_passed_or_failed() -> None:
    assert not main_due(run("aaa", 0), "aaa")
    assert not main_due(run("aaa", 1), "aaa")


def test_a_failure_whose_search_was_cut_short_is_due_again_on_the_same_tip() -> None:
    assert main_due(run("aaa", 1, passed="000"), "aaa")
    assert not main_due(run("aaa", 1, passed="000", searched=True), "aaa")
    assert not main_due(run("aaa", 1), "aaa")  # no pass to search from


def test_the_failing_step_is_the_first_the_log_leaves_failed() -> None:
    # gate: web-unit failed then passed; rust-test failed and stays failed; web-e2e failed too
    reported = [
        ("preflight", "passed"),
        ("web-unit", "passed"),
        ("rust-test", "failed"),
        ("web-e2e", "failed"),
    ]
    assert failed_step(reported) == "rust-test"
    assert failed_step([("preflight", "passed")]) == ""
    assert failed_step([]) == ""


def test_a_failure_before_any_step_is_named_by_the_last_line_of_the_log() -> None:
    log = "pulling image\ndocker: image not found\n\n"
    assert cause_before_any_step(log) == "before any step: docker: image not found"
    assert cause_before_any_step("") == "before any step"
    assert cause_before_any_step("x" * 300) == "before any step: " + "x" * 120


def _scan(count: int, broken: int) -> int | None:
    return next((i for i in range(count) if i >= broken), None)


def test_bisection_finds_the_first_failing_commit_in_few_runs() -> None:
    for count in range(13):
        for broken in range(count + 1):
            for last_fails in (False, True):
                if last_fails and count in (0, broken):
                    continue
                asked: list[int] = []

                def fails(i: int, asked: list[int] = asked, broken: int = broken) -> bool:
                    asked.append(i)
                    return i >= broken

                found = bisect(count, last_fails, fails)
                bound = (count + 1).bit_length()
                assert found == _scan(count, broken), (count, broken, last_fails)
                assert all(i < count for i in asked)
                assert not (last_fails and count - 1 in asked)
                assert len(asked) <= bound


def test_a_failed_run_ends_the_search_with_its_error() -> None:
    asked = []

    def fails(i: int) -> bool:
        asked.append(i)
        message = "slept"
        raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="slept"):
        bisect(8, False, fails)
    assert len(asked) == 1


def test_a_pass_moves_the_last_pass_to_its_commit() -> None:
    done = complete_main(run("bbb", 1, passed="aaa"), run("ccc", 0), step="", reason="")
    assert done.passed == "ccc"
    assert done.step == ""


def test_a_failure_keeps_the_last_pass_and_names_its_step_and_reason() -> None:
    done = complete_main(
        run("aaa", 0, passed="aaa"), run("bbb", 101), step="rust-test", reason="build failed"
    )
    assert (done.passed, done.step, done.reason, done.searched) == (
        "aaa",
        "rust-test",
        "build failed",
        False,
    )


def test_a_streak_on_the_same_step_keeps_the_first_blamed_merge() -> None:
    before = run("bbb", 1, passed="aaa", step="rust-test", broken_by="m1", searched=True)
    done = complete_main(before, run("ccc", 1), step="rust-test", reason="")
    assert (done.broken_by, done.searched, done.passed) == ("m1", True, "aaa")


def test_a_streak_that_moves_to_another_step_searches_again() -> None:
    before = run("bbb", 1, passed="aaa", step="rust-test", broken_by="m1", searched=True)
    done = complete_main(before, run("ccc", 1), step="web-e2e", reason="")
    assert (done.broken_by, done.searched) == ("", False)


def test_a_run_that_could_not_start_inherits_no_streak() -> None:
    before = run("bbb", 1, passed="aaa", step="rust-test", broken_by="m1", searched=True)
    done = complete_main(before, run("ccc", -1), step="before any step", reason="")
    assert (done.broken_by, done.searched) == ("", False)


@pytest.mark.parametrize(
    ("branch", "second", "known", "expected"),
    [
        ("ticket/cf-12", "", {"CF-12"}, "CF-12"),  # id in the branch name that names a ticket
        ("ticket/cf-12", "", set(), "CF-12"),  # any id in the branch name as a last resort
        ("feature/x", "Fix CF-7 and CF-8", set(), "CF-7"),  # first id of the second parent
        ("feature/cf-3-and-cf-4", "Fix CF-7", {"CF-4"}, "CF-4"),  # known beats first
        ("feature/x", "no id here", set(), ""),
        ("", "", set(), ""),
    ],
)
def test_a_merge_is_blamed_on_the_ticket_its_branch_or_second_parent_names(
    branch: str, second: str, known: set[str], expected: str
) -> None:
    assert blame_ticket(branch, second, known) == expected


def test_one_hour_after_a_window_of_main_is_not_a_rule() -> None:
    assert timedelta(hours=1) == timedelta(seconds=3600)


def test_a_bisection_asks_one_commit_at_a_time_and_remembers_the_answers() -> None:
    steps = Bisection(4, last_fails=False)
    asked = []
    while (index := steps.next_index()) is not None:
        asked.append(index)
        steps.answer(failed=index >= 1)  # the second commit is the first to fail
    assert (asked, steps.found) == ([2, 1, 0], 1)


def test_a_bisection_that_finds_nothing_ends_with_none() -> None:
    steps = Bisection(3, last_fails=False)
    while steps.next_index() is not None:
        steps.answer(failed=False)
    assert steps.found is None


def test_the_merges_on_the_first_parent_line_come_oldest_first_and_skip_a_branchs_own() -> None:
    # tip m3 merges f2 (a side branch holding m2, itself a merge); first-parent line m3, c2, m1
    parents = {
        "m3": ["c2", "f2"],
        "f2": ["m2"],
        "m2": ["x1", "x2"],  # a merge inside the side branch: not on the first-parent line
        "c2": ["m1"],
        "m1": ["c0", "f1"],
        "f1": ["c0"],
    }
    assert first_parent_merges(parents, "m3") == ["m1", "m3"]


def test_a_tip_that_is_no_merge_and_commits_outside_the_range_end_the_line() -> None:
    assert first_parent_merges({"t": ["u"]}, "t") == []
    assert first_parent_merges({}, "t") == []
