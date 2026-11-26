"""What a checks log says of its phases, and the lines a run appends."""

import pytest

from code_factory.checks.models import Phases
from code_factory.checks.rules import phases_line, phases_of, timing_line

LOG = """\
gate: rust-test runs the tests of core and their dependents: the branch changed those crates
gate: rust-lint waited 15s for the heavy-step lock
gate: rust-test waited 5s for the heavy-step lock
gate: rust-test starts
   Compiling core v0.1.0
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 99.00s
    Finished `test` profile [unoptimized + debuginfo] target(s) in 1m 02s
    Finished `test` profile [unoptimized + debuginfo] target(s) in 0.50s
     Summary [ 313.250s] 3179 tests run: 3179 passed, 15 skipped
     Summary [   2.000s] 4 tests run: 4 passed
"""


def test_a_log_gives_its_compile_test_and_wait_seconds() -> None:
    found = phases_of(LOG)
    # 62 + 0.5 compiled, 313.25 + 2 ran, 15 + 5 waited
    assert (found.compile, found.tests, found.heavy_wait) == (62.5, 315.25, 20.0)
    assert found.scope == "the tests of core and their dependents: the branch changed those crates"


def test_a_log_without_phases_reads_as_zero() -> None:
    assert phases_of("gate: preflight passed in 1s\n") == Phases()


def test_pytests_last_line_adds_to_the_test_seconds() -> None:
    log = "=== 12 passed in 313.25s (0:05:13) ===\n=== 3 passed in 1.75s ===\n"
    assert phases_of(log).tests == 313.25


def test_the_phases_line_names_the_head_the_scope_and_three_durations() -> None:
    line = phases_line("abc123", 7.0, phases_of(LOG))
    assert line == (
        "code-factory checks phases: head abc123, scope the tests of core and their dependents: "
        "the branch changed those crates, wait 27.000s, compile 62.500s, tests 315.250s"
    )
    assert phases_line("abc123", 0.0, Phases()) == (
        "code-factory checks phases: head abc123, scope none, wait 0.000s, compile 0.000s, "
        "tests 0.000s"
    )


def test_the_timing_line_lists_total_wait_setup_and_command() -> None:
    assert timing_line(10.0, 2.5, 1.25, 6.0) == (
        "code-factory checks timing: 10.000s total, 2.500s container and heavy lock, "
        "1.250s setup, 6.000s command and verdict"
    )


@pytest.mark.parametrize("took", ["12.5s", "1m 02s", "0.50s"])
def test_both_duration_forms_are_read(took: str) -> None:
    seconds = {"12.5s": 12.5, "1m 02s": 62.0, "0.50s": 0.5}[took]
    log = f"    Finished `test` profile [x] target(s) in {took}\n"
    assert phases_of(log).compile == seconds
