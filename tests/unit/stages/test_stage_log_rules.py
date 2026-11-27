"""What a checks log says. Expected values: the previous implementation's killed-run, build-failure
and fix-loop tests (exact strings), its log line grammar, and pytest's own summary forms."""

import pytest

from code_factory.stages.rules import (
    killed_by_system,
    killed_run,
    last_started_step,
    no_verdict,
    read_log,
)
from code_factory.stages.service import StageService

TEST_FAILED = """\
gate: rust-test starts
   Compiling core v0.1.0 (/w/crates/core)
        FAIL [   0.412s] core::suite board_rules::a_ticket_moves
  stderr ───
    thread 'board_rules::a_ticket_moves' panicked at tests/suite/board_rules.rs:9:5
error: test run failed
gate: rust-test failed (exit 100) after 61s
"""

MISSING_CRATE = """\
gate: rust-test starts
   Compiling idna_adapter v1.2.0
error[E0463]: can't find crate for `idna_adapter`
For more information about this error, try `rustc --explain E0463`.
error: could not compile `url` (lib) due to 1 previous error
gate: rust-test failed (exit 101) after 49s
"""

LINK_FAILED = """\
gate: rust-test starts
error: linking with `cc` failed: exit status: 1
error: could not compile `app` (bin "app") due to 1 previous error
gate: rust-test failed (exit 101) after 474s
"""

TYPE_ERROR = (
    "error[E0308]: mismatched types\nerror: could not compile `a` (lib) due to 1 previous error\n"
)

PYTEST_IMPORT = """\
==================================== ERRORS ====================================
_____________________ ERROR collecting tests/test_a.py ______________________
tests/test_a.py:1: in <module>
    import missing
E   ModuleNotFoundError: No module named 'missing'
=========================== short test summary info ============================
ERROR tests/test_a.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
"""

PYTEST_SYNTAX = """\
_____________________ ERROR collecting tests/test_b.py ______________________
E     File "tests/test_b.py", line 1
E       def (:
E   SyntaxError: invalid syntax
"""

PYTEST_FAILED = """\
=================================== FAILURES ===================================
=========================== short test summary info ============================
FAILED tests/test_b.py::TestMore::test_method - assert 1 == 2
FAILED tests/test_a.py::test_it
============================== 2 failed, 3 passed in 0.12s =====================
"""


def test_exit_137_and_minus_one_give_no_verdict_and_every_other_code_does() -> None:
    codes = [137, -1, 0, 1, 2, 101, 136, 138]

    assert [no_verdict(code) for code in codes] == [
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
    ]


def test_the_exit_codes_of_a_signal_are_a_kill_and_their_neighbours_are_not() -> None:
    assert all(killed_by_system(code) for code in (137, 143, -9, -15))
    assert not any(killed_by_system(code) for code in (0, 1, 2, -1, 136, 138, 142, 144))


def test_a_kill_code_with_no_failed_step_line_is_a_killed_run() -> None:
    assert killed_run(137, "gate: vite-build starts\ntransforming...\n")


def test_a_failed_step_line_makes_a_kill_code_an_ordinary_failure() -> None:
    log = "gate: rust-test starts\ngate: rust-test failed (exit 137)\n"

    assert not killed_run(137, log)


def test_only_a_failed_step_line_disqualifies_a_kill() -> None:
    log = "gate: a starts\ntest x_failed ... ok\ngate: a quarantined: t failed\n"

    assert killed_run(143, log)


def test_an_ordinary_exit_is_no_killed_run_whatever_the_log_says() -> None:
    assert not killed_run(1, "gate: a starts\n")


def test_the_last_started_step_is_where_a_killed_log_ends() -> None:
    log = "gate: fmt starts\ngate: fmt passed in 1s\ngate: web-build starts\ntransforming...\n"

    assert last_started_step(log) == "web-build"
    assert last_started_step("compiling\nerror\n") is None


def test_the_failing_lines_name_a_failure_by_a_whole_word_in_log_order() -> None:
    log = (
        "Compiling a\n"
        "test board::a_failed_move_is_undone ... ok\n"
        "test follow::starts ... FAILED\n"
        "thread 'x' panicked at src/a.rs:3\n"
        "error: test failed\n"
        "gate: rust-test failed (exit 101) after 9s\n"
    )

    assert read_log(log).failing_lines == [
        "test follow::starts ... FAILED",
        "thread 'x' panicked at src/a.rs:3",
        "error: test failed",
        "gate: rust-test failed (exit 101) after 9s",
    ]


def test_a_log_naming_no_failure_gives_its_last_line_and_an_empty_log_none() -> None:
    assert read_log("one\ntwo\n").failing_lines == ["two"]
    assert read_log("").failing_lines == []


def test_failing_tests_are_the_libtest_lines_reported_failed_once_each_sorted() -> None:
    log = (
        "test b::two ... FAILED\ntest a::one ... ok\ntest a::three ... FAILED\n"
        "test b::two ... FAILED\nerror: test failed, to rerun\n"
        "gate: rust-test failed (exit 101)\n"
    )

    assert read_log(log).failing_tests == ["a::three", "b::two"]
    assert read_log("all ok\n").failing_tests == []


def test_failing_tests_include_the_pytest_short_summary_nodes() -> None:
    assert read_log(PYTEST_FAILED).failing_tests == [
        "tests/test_a.py::test_it",
        "tests/test_b.py::TestMore::test_method",
    ]


def test_a_failing_test_is_not_a_build_failure_even_beside_compiler_text() -> None:
    assert not read_log(TEST_FAILED).build_failure
    assert read_log(TEST_FAILED).failure_reason == ""
    assert not read_log(MISSING_CRATE + TEST_FAILED).build_failure


def test_a_missing_crate_and_a_failed_link_are_build_failures_of_the_environment() -> None:
    for log in (MISSING_CRATE, LINK_FAILED):
        reading = read_log(log)
        assert reading.build_failure
        assert reading.failure_reason == "build failed: environment"


def test_any_other_compiler_error_means_the_tree_does_not_compile() -> None:
    assert read_log(TYPE_ERROR).failure_reason == "build failed"
    assert read_log(MISSING_CRATE + TYPE_ERROR).failure_reason == "build failed"
    assert read_log("error[E0599]: no method\n").failure_reason == "build failed"


def test_a_log_with_no_compile_error_says_nothing_of_the_build() -> None:
    assert not read_log("gate: web-unit failed (exit 1) after 9s\n").build_failure
    assert not read_log("").build_failure


def test_a_pytest_collection_error_is_a_build_failure_and_a_missing_module_is_environmental() -> (
    None
):
    assert read_log(PYTEST_IMPORT).build_failure
    assert read_log(PYTEST_IMPORT).failure_reason == "build failed: environment"


def test_a_pytest_syntax_error_is_a_build_failure_of_the_tree() -> None:
    assert read_log(PYTEST_SYNTAX).failure_reason == "build failed"


def test_a_pytest_collection_error_beside_a_failed_test_is_a_test_failure() -> None:
    assert read_log(PYTEST_IMPORT + PYTEST_FAILED).failure_reason == ""


def test_the_gate_lines_give_each_step_its_last_state_in_first_seen_order() -> None:
    log = (
        "gate: fmt due\n"
        "gate: fmt passed in 3s\n"
        "gate: web-build due: waiting\n"
        "gate: rust-test failed (exit 101) after 9s\n"
        "not a gate line\n"
        "gate: bad step passed in 2s\n"
        "gate: rust-test passed in 7s\n"
    )

    reading = read_log(log)

    assert reading.reported_steps == [
        ("fmt", "passed"),
        ("web-build", "due"),
        ("rust-test", "passed"),
    ]
    assert reading.step_seconds == [("fmt", 3), ("rust-test", 7)]


def test_a_step_last_failed_has_no_seconds() -> None:
    log = "gate: a passed in 4s\ngate: a failed (exit 1) after 5s\n"

    assert read_log(log).step_seconds == []
    assert read_log(log).reported_steps == [("a", "failed")]


def test_heavy_step_lock_waits_are_summed_per_step() -> None:
    log = (
        "gate: a waited 3s for the heavy-step lock\n"
        "gate: b waited 1s for the heavy-step lock\n"
        "gate: a waited 4s for the heavy-step lock\n"
        "gate: a waited xs for the heavy-step lock\n"
    )

    assert read_log(log).lock_waits == [("a", 7), ("b", 1)]


def test_quarantined_failures_count_their_lines_per_test() -> None:
    log = (
        "gate: a quarantined: t::one failed\n"
        "gate: a quarantined: t::two failed\n"
        "gate: a quarantined: t::one failed\n"
        "gate: a quarantined:  failed\n"
    )

    assert read_log(log).quarantined_failures == [("t::one", 2), ("t::two", 1)]


def test_flaky_steps_are_named_once_in_first_seen_order() -> None:
    log = (
        "gate: b flaky: passed on rerun\ngate: a flaky: x\n"
        "gate: b flaky: again\ngate: c passed in 1s\n"
    )

    assert read_log(log).flaky_steps == ["b", "a"]


@pytest.mark.parametrize("line", ["gate: a  flaky:", "gate: flaky:"])
def test_a_gate_line_without_a_step_names_none(line: str) -> None:
    assert read_log(line + "\n").flaky_steps == []


def test_the_service_reads_a_log_with_or_without_the_exit_code_of_its_run() -> None:
    plain = StageService.read_log(TEST_FAILED)

    assert StageService.read_log(TEST_FAILED, exit_code=100) == plain
    assert StageService.read_log(TEST_FAILED, 100) == plain
    assert plain.failing_lines == read_log(TEST_FAILED).failing_lines


@pytest.mark.parametrize(
    ("log", "build_failure"),
    [
        ("error: could not compile `app`\n", True),
        ("error: could not compile `app`\ntest parse::tests::bad ... FAILED\n", False),
        ("error: could not compile `app`\nFAILED tests/test_a.py::test_x\n", False),
        ("E   SyntaxError: invalid syntax\n", True),
        ("ERROR collecting tests/test_a.py\n", True),
        ("x = 'E   SyntaxError'\n", False),
    ],
)
def test_a_build_failure_is_a_build_error_with_no_failed_test(
    log: str, *, build_failure: bool
) -> None:
    assert read_log(log).build_failure is build_failure
