from code_factory.sessions.models import Failure, Recurrence
from code_factory.sessions.rules.repeats import (
    failures,
    output_text,
    printed,
    recurring,
    statement,
)


def session(session_id: str, *steps: tuple[str, int]) -> tuple[str, list[Failure]]:
    return session_id, [Failure(step, code) for step, code in steps]


def test_a_failure_line_names_its_step_and_exit_code() -> None:
    output = "running\ngate: pytest failed (exit 100)\n  gate: web-lint failed (exit 1)  \n"
    assert failures(output) == [Failure("pytest", 100), Failure("web-lint", 1)]


def test_lines_that_are_not_a_failure_are_not_read() -> None:
    lines = [
        "gate: pytest passed in 12s",
        "gate: pytest quarantined: some_test failed",
        "gate: pytest flaky: failed once",
        "note that gate: pytest failed (exit 1) came up",
        "gate: Rust Test failed (exit 1)",
        "gate: pytest failed (exit x)",
        "gate: pytest failed (exit 1) and more",
        "gate: pytest failed (exit )",
        "gate: pytest failed (exit 1000)",
        "gate:  failed (exit 1)",
    ]
    assert failures("\n".join(lines)) == []


def test_the_same_failure_in_three_sessions_is_one_recurrence_naming_them() -> None:
    found = recurring(
        [
            session("c", ("pytest", 100)),
            session("a", ("pytest", 100)),
            session("b", ("pytest", 100), ("web-lint", 1)),
        ]
    )
    assert found == [Recurrence(Failure("pytest", 100), ["a", "b", "c"])]


def test_two_sessions_are_not_a_recurrence() -> None:
    assert recurring([session("a", ("pytest", 100)), session("b", ("pytest", 100))]) == []


def test_one_session_failing_three_times_counts_once() -> None:
    assert recurring([session("a", *[("pytest", 100)] * 3)]) == []


def test_another_exit_code_is_another_reason() -> None:
    found = recurring(
        [
            session("a", ("pytest", 100)),
            session("b", ("pytest", 101)),
            session("c", ("pytest", 100)),
        ]
    )
    assert found == []


def test_recurrences_are_ordered_by_step_and_code() -> None:
    ids = ["a", "b", "c"]
    found = recurring([session(i, ("web-lint", 1), ("pytest", 2), ("pytest", 1)) for i in ids])
    assert [r.failure for r in found] == [
        Failure("pytest", 1),
        Failure("pytest", 2),
        Failure("web-lint", 1),
    ]


def test_the_statement_holds_the_step_and_code_and_no_count() -> None:
    text = statement(Failure("ruff", 101))
    assert "ruff" in text
    assert "exit 101" in text
    assert "3" not in text


def test_a_tool_output_is_read_whole_or_by_the_gate_lines_a_trimmed_one_kept() -> None:
    line = "gate: pytest failed (exit 1)"
    assert printed("a\n" + line) == "a\n" + line
    assert printed({"_trimmed_chars": 9000, "head": "noise", "gates": [line, 5]}) == line
    assert printed({"stdout": "out", "stderr": {"gates": [line]}}) == "out\n" + line
    assert printed({"_trimmed_chars": 9000, "head": "noise"}) == ""
    assert printed(None) == ""
    assert output_text({"stdout": "o"}, line) == "o\n" + line
    assert failures(output_text({"stderr": {"gates": [line]}}, None)) == [Failure("pytest", 1)]
