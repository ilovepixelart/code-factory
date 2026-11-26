"""Which failure makes a pass on a tree flaky. No previous test exists: every case is worked by hand
from the rule (the first failure on the tree since the last `flaky` record that is not a system kill
and not slept; else the first pass that is not clean while no `flaky` record names the tree)."""

from datetime import UTC, datetime

from code_factory.stages.models import Record
from code_factory.stages.rules import flaky_failure, flaky_reason

AT = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)


def checks(code: int, log: str, tree: str = "t1", **more: object) -> Record:
    return Record(kind="checks", at=AT, data={"exit_code": code, "log": log, "tree": tree, **more})


def flaky(tree: str = "t1") -> Record:
    return Record(kind="flaky", at=AT, data={"tree": tree})


def test_the_first_failure_on_the_tree_is_the_one_a_later_pass_is_flaky_after() -> None:
    history = [checks(1, "log-a"), checks(1, "log-b"), checks(0, "log-c")]

    assert flaky_failure(history, "t1") == "log-a"


def test_a_tree_that_only_passed_cleanly_is_not_flaky() -> None:
    assert flaky_failure([checks(0, "log-a")], "t1") is None


def test_a_flaky_record_clears_the_failures_before_it_and_a_later_failure_counts_again() -> None:
    assert flaky_failure([checks(1, "log-a"), flaky()], "t1") is None
    assert flaky_failure([checks(1, "log-a"), flaky(), checks(1, "log-b")], "t1") == "log-b"


def test_a_pass_that_ran_a_step_twice_is_the_flaky_one_while_no_flaky_record_names_the_tree() -> (
    None
):
    unclean = checks(0, "log-p", retried=["web-unit"])

    assert flaky_failure([unclean], "t1") == "log-p"
    assert flaky_failure([flaky(), unclean], "t1") is None


def test_a_pass_whose_log_was_unread_is_not_clean() -> None:
    assert flaky_failure([checks(0, "log-u", log_unread=True)], "t1") == "log-u"


def test_a_failure_the_machine_sleeping_caused_is_excused() -> None:
    assert flaky_failure([checks(1, "log-s", slept=True)], "t1") is None


def test_a_run_the_system_killed_is_no_failure_of_the_tree() -> None:
    assert flaky_failure([checks(137, "log-k", outcome="killed"), checks(0, "log-p")], "t1") is None


def test_records_of_another_tree_are_ignored() -> None:
    assert flaky_failure([checks(1, "log-a", tree="t2")], "t1") is None
    assert flaky_failure([checks(1, "log-a"), flaky("t2")], "t1") == "log-a"


OPENING = "Filed by the board when the checks of CF-7 passed on tree t1"


def test_the_reason_names_the_steps_that_passed_only_on_the_second_run() -> None:
    history = [checks(0, "log-p", retried=["web-unit", "rust-test"])]

    assert flaky_reason(history, "CF-7", "t1", "log-p") == (
        f"{OPENING} with web-unit, rust-test failing and then passing when the gate ran it "
        "again. The run is logged at log-p."
    )


def test_the_reason_names_a_log_that_could_not_be_read() -> None:
    history = [checks(0, "log-u", log_unread=True)]

    assert flaky_reason(history, "CF-7", "t1", "log-u") == (
        f"{OPENING} with a log that could not be read when they were recorded: log-u."
    )


def test_the_reason_of_a_failure_before_a_pass_names_the_failed_run() -> None:
    history = [checks(1, "log-a"), checks(0, "log-p")]

    assert flaky_reason(history, "CF-7", "t1", "log-a") == (
        f"{OPENING} after failing there. The failed run is logged at log-a."
    )


# A run that gave no verdict (-1: the tree moved, or it never started) did not fail: a pass after
# it is no flaky check, and filing one sent an agent after a bug that does not exist.
def test_a_run_with_no_verdict_before_a_pass_is_not_a_failure() -> None:
    assert flaky_failure([checks(-1, "log-a"), checks(0, "log-b")], "t1") is None


def test_a_real_failure_after_a_run_with_no_verdict_still_counts() -> None:
    history = [checks(-1, "log-a"), checks(1, "log-b"), checks(0, "log-c")]

    assert flaky_failure(history, "t1") == "log-b"
