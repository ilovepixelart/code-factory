"""The fix loop's readers, translated case by case from the previous implementation's fix-loop
tests: what sends a pull request back, when a round was already given, what stands once the rounds
ran out, the retry of a failed head, and the task a failed head's agent is told."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from code_factory.stages.models import (
    FixHalt,
    FixRound,
    MainCheckView,
    PullView,
    Record,
)
from code_factory.stages.rules import (
    CONTAINER_UNAVAILABLE,
    attempts_of,
    checks_task,
    conflict_hold,
    container_retry_due,
    decide_round,
    failed_steps,
    fails_on_main,
    feedback_reason,
    halted_at,
    own_checks,
    rerun_pending,
    round_given,
    rounds_left,
    rounds_out,
    settled,
    waits_on_main,
)

T0 = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)


def pull(**fields: Any) -> PullView:  # noqa: ANN401  # keyword fields of the model
    return PullView.model_validate(
        {"state": "open", "review": "", "ci": "none", "head": "h1", **fields}
    )


def record(kind: str, at: datetime = T0, **data: Any) -> Record:  # noqa: ANN401
    return Record(kind=kind, at=at, data=data)


def ran(code: int, tree_id: str = "t", head: str = "h1", **more: Any) -> Record:  # noqa: ANN401
    return record("checks", commit=head, exit_code=code, tree_id=tree_id, **more)


def test_the_boards_failed_checks_send_the_pull_request_back_and_a_pass_hides_nothing() -> None:
    quiet, red = pull(), pull(ci="failed")

    assert feedback_reason(quiet, 1) == "ci"
    assert feedback_reason(quiet, 0) == ""
    assert feedback_reason(quiet, None) == ""
    assert feedback_reason(red, 0) == "ci"
    assert feedback_reason(red, None) == "ci"


def test_checks_without_a_verdict_are_no_failure_of_the_code_but_a_review_still_counts() -> None:
    red = pull(ci="failed", other_ci="none")
    asked = pull(ci="failed", other_ci="none", review="changes_requested")

    assert feedback_reason(red, 137) == ""
    assert feedback_reason(red, -1) == ""
    assert feedback_reason(asked, 137) == "review"
    assert feedback_reason(asked, 1) == "ci"


def test_the_boards_own_status_on_github_is_not_read_as_ci() -> None:
    own_only = pull(ci="failed", other_ci="none")
    others = pull(ci="failed", other_ci="failed")
    same = pull(ci="failed")

    assert (feedback_reason(own_only, 0), feedback_reason(own_only, None)) == ("", "")
    assert (feedback_reason(others, 0), feedback_reason(others, 137)) == ("ci", "ci")
    assert feedback_reason(same, 137) == "ci"


def test_the_boards_pending_retry_does_not_hide_a_failed_external_check() -> None:
    assert feedback_reason(pull(own_pending=True), 1) == ""
    assert feedback_reason(pull(own_pending=True, ci="failed", other_ci="failed"), 1) == "ci"


def test_a_pull_request_that_is_not_open_is_not_sent_back() -> None:
    merged = pull(state="merged", ci="failed", review="changes_requested")

    assert feedback_reason(merged, 1) == ""


def test_the_latest_checks_record_that_names_the_head_is_the_boards_checks_on_it() -> None:
    history = [ran(137, head="h1"), ran(1, head="h2"), ran(0, head="h1")]

    assert [(own_checks(history, h) or (None, None))[1] for h in ("h1", "h2", "h3")] == [0, 1, None]


def test_a_checks_record_without_an_exit_code_is_no_verdict_at_all() -> None:
    assert own_checks([record("checks", commit="h1")], "h1") is None


@pytest.mark.parametrize(
    ("codes", "expected"),
    [
        ([], (False, False)),
        ([1], (False, True)),
        ([137], (False, False)),
        ([0], (True, False)),
        ([1, 0], (True, False)),
        ([1, 1], (True, False)),
        ([137, 1], (False, True)),
        ([1, -1], (False, True)),
        ([1, -1, 1], (True, False)),
        ([1, -1, 0], (True, False)),
        ([1, 137, -1], (True, False)),
    ],
)
def test_a_failure_runs_once_more_on_its_tree_before_the_head_is_settled(
    codes: list[int], expected: tuple[bool, bool]
) -> None:
    history = [ran(code) for code in codes]

    verdict = (settled(history, "h1"), rerun_pending(history, "h1"))
    assert verdict == expected


def test_a_record_without_a_tree_id_says_nothing_of_the_commit() -> None:
    history = [ran(1, tree_id="")]

    assert (settled(history, "h1"), rerun_pending(history, "h1")) == (False, False)


def test_attempts_count_only_the_head_and_report_each_kind() -> None:
    history = [ran(1), ran(137), ran(0, head="h2")]

    assert attempts_of(history, "h1") == (False, 1, 1)


def test_container_unavailability_retries_without_spending_code_attempts() -> None:
    unavailable = record(
        "checks", commit="h1", tree_id="t1", exit_code=-1, reason=CONTAINER_UNAVAILABLE
    )
    history = [unavailable, unavailable]

    assert not settled(history, "h1")
    assert not container_retry_due(history, "h1", T0 + timedelta(seconds=59))
    assert container_retry_due(history, "h1", T0 + timedelta(seconds=60))
    assert container_retry_due(history, "h2", T0)


def test_a_head_without_checks_or_with_a_real_verdict_is_due_at_once() -> None:
    assert container_retry_due([], "h1", T0)
    assert container_retry_due([ran(137)], "h1", T0)
    assert container_retry_due([ran(1)], "h1", T0)


def test_the_failed_steps_of_a_checks_record_are_those_reported_failed() -> None:
    check = record("checks", steps={"fmt": "passed", "rust-test": "failed", "web": "failed"})

    assert failed_steps(check) == ["rust-test", "web"]
    assert failed_steps(record("checks")) == []


def test_a_failure_is_mains_where_step_and_tests_agree() -> None:
    steps, tests = ["rust-fmt", "rust-test"], ["a::b"]

    def found(main: MainCheckView, main_tests: list[str]) -> str | None:
        return fails_on_main(steps, tests, main, main_tests)

    assert found(MainCheckView(exit_code=101, step="rust-test"), tests) == "rust-test"
    assert found(MainCheckView(exit_code=0), tests) is None
    assert found(MainCheckView(exit_code=137, step="rust-test"), tests) is None
    assert found(MainCheckView(exit_code=101, step="rust-lint"), tests) is None
    assert found(MainCheckView(exit_code=101, step="rust-test"), ["a::c"]) is None
    assert found(MainCheckView(exit_code=101, step="rust-test"), []) is None


def test_the_status_line_says_where_main_fails_too() -> None:
    assert waits_on_main("rust-test") == "Fails on main too at rust-test"


def test_a_round_is_given_once_per_failed_head_and_reason() -> None:
    given = [FixRound(head="h1", reason="ci", review="", run_id="", at=T0)]

    assert round_given(given, pull(), "ci")
    assert not round_given(given, pull(head="h2"), "ci")
    assert not round_given(given, pull(), "conflict")
    assert not round_given([], pull(), "ci")


def test_a_review_has_one_round_on_whatever_head_it_stands() -> None:
    first = "2026-11-11T09:00:00Z"
    given = [FixRound(head="h1", reason="review", review=first, run_id="", at=T0)]

    assert round_given(given, pull(head="h1", reviewed=first), "review")
    assert round_given(given, pull(head="h2", reviewed=first), "review")
    assert not round_given(given, pull(head="h1", reviewed="2026-11-12T09:00:00Z"), "review")


def test_a_review_round_without_its_review_counts_for_its_head() -> None:
    before = [FixRound(head="h1", reason="review", review="", run_id="", at=T0)]
    named = [FixRound(head="h1", reason="review", review="2026-11-11T09:00:00Z", run_id="", at=T0)]
    stamp = "2026-11-11T09:00:00Z"

    assert round_given(before, pull(head="h1", reviewed=stamp), "review")
    assert not round_given(before, pull(head="h2", reviewed=stamp), "review")
    assert round_given(named, pull(head="h1", reviewed=""), "review")
    assert not round_given(named, pull(head="h2", reviewed=""), "review")


def halted(reason: str, head: str = "h1", rounds: int = 3, at: datetime = T0) -> FixHalt:
    return FixHalt(head=head, reason=reason, rounds=rounds, at=at)


CONFLICT = record("merge_conflict", tip="h1", main="m", **{"with": "origin/main"}, files="f.txt")


def test_rounds_that_ran_out_name_what_still_stands() -> None:
    assert rounds_out([halted("ci")], [], pull(ci="failed")) == "Fixes stopped after 3 rounds"
    assert (
        rounds_out([halted("ci")], [record("checks", commit="h1", exit_code=101)], pull())
        == "Fixes stopped after 3 rounds"
    )
    assert (
        rounds_out([halted("review")], [], pull(review="changes_requested"))
        == "Fixes stopped after 3 rounds: a review still requests changes"
    )
    assert (
        rounds_out([halted("conflict")], [CONFLICT], pull())
        == "Fixes stopped after 3 rounds: conflicts with origin/main in f.txt"
    )


def test_one_round_is_named_in_the_singular() -> None:
    assert (
        rounds_out([halted("ci", rounds=1)], [], pull(ci="failed")) == "Fixes stopped after 1 round"
    )


def test_a_stale_failed_aggregate_with_the_other_checks_passing_clears_a_ci_halt() -> None:
    stale = pull(ci="failed", other_ci="passed")
    own_passed = [record("checks", commit="h1", exit_code=0)]

    assert rounds_out([halted("ci")], own_passed, stale) is None
    own_failed = [record("checks", commit="h1", exit_code=1)]
    assert rounds_out([halted("ci")], own_failed, stale) == "Fixes stopped after 3 rounds"


def test_rounds_that_ran_out_name_nothing_once_the_cause_is_gone() -> None:
    cleared = record("merge_conflict_cleared", tip="h1")

    assert rounds_out([halted("ci")], [], pull()) is None
    assert rounds_out([halted("review")], [], pull()) is None
    assert rounds_out([halted("conflict")], [CONFLICT, cleared], pull()) is None
    assert rounds_out([], [CONFLICT], pull()) is None
    assert rounds_out([], [], pull(review="changes_requested")) is None


def test_rounds_that_ran_out_on_another_head_or_a_closed_pull_request_name_nothing() -> None:
    assert rounds_out([halted("review")], [], pull(head="h2", review="changes_requested")) is None
    assert rounds_out([halted("ci")], [], pull(state="merged", ci="failed")) is None


def test_a_conflict_holds_only_the_tip_it_was_found_on_until_a_later_check_clears_it() -> None:
    assert conflict_hold([CONFLICT], "h1") == "conflicts with origin/main in f.txt"
    assert conflict_hold([CONFLICT], "h2") == ""
    assert conflict_hold([CONFLICT, record("merge_conflict_cleared", tip="h1")], "h1") == ""
    assert conflict_hold([], "h1") == ""


def test_the_moment_the_rounds_ran_out_on_a_head_is_that_of_its_latest_halt() -> None:
    halts = [
        halted("review", "h1", at=datetime(2026, 11, 12, 11, tzinfo=UTC)),
        halted("review", "h2", at=datetime(2026, 11, 12, 12, tzinfo=UTC)),
        halted("ci", "h1", at=datetime(2026, 11, 12, 13, tzinfo=UTC)),
    ]

    assert halted_at(halts, "h1") == datetime(2026, 11, 12, 13, tzinfo=UTC)
    assert halted_at(halts, "h3") is None


@pytest.mark.parametrize(("count", "left"), [(0, 3), (2, 1), (3, 0), (4, 0)])
def test_the_rounds_left_stop_at_zero_around_the_cap(count: int, left: int) -> None:
    assert rounds_left(count, 3) == left


@pytest.mark.parametrize(
    ("count", "can_start", "given", "outcome"),
    [
        (2, True, False, "started"),
        (3, True, False, "halted"),
        (4, True, False, "halted"),
        (2, False, False, "waiting"),
        (2, True, True, "given"),
        (3, True, True, "given"),
    ],
)
def test_a_round_is_given_halted_waiting_or_started(
    count: int, can_start: bool, given: bool, outcome: str
) -> None:
    assert decide_round(count, 3, can_start=can_start, given=given) == outcome


def mask(text: str) -> str:
    return text.replace("abc123", "[redacted]")


def test_the_checks_task_names_the_step_the_exit_code_and_the_failing_lines() -> None:
    lines = ["test follow::starts ... FAILED", "error: test failed"]

    assert checks_task("0123456789abcdef", 101, ["rust-test"], lines, mask) == (
        "The board's checks failed on 0123456789ab at rust-test (exit 101). Their log says:\n"
        "test follow::starts ... FAILED\nerror: test failed\n"
        "Fix the cause on this branch, and keep every test green."
    )
    assert checks_task("0123456789abcdef", 1, [], ["boom"], mask) == (
        "The board's checks failed on 0123456789ab (exit 1). Their log says:\nboom\n"
        "Fix the cause on this branch, and keep every test green."
    )


def test_the_checks_task_without_log_lines_quotes_none() -> None:
    assert checks_task("0123456789abcdef", 1, ["rust-test"], [], mask) == (
        "The board's checks failed on 0123456789ab at rust-test (exit 1). Fix the cause on this "
        "branch, and keep every test green."
    )


def test_the_checks_task_masks_then_cuts_each_line_to_500_characters() -> None:
    secret = 'error: {"token": "abc123"}'  # noqa: S105  # a masking input, not a credential
    long = "error " + "x" * 600

    task = checks_task("h", 1, [], [secret, long], mask)

    quoted = task.splitlines()[1:3]
    assert quoted[0] == 'error: {"token": "[redacted]"}'
    assert quoted[1] == "error " + "x" * 494
