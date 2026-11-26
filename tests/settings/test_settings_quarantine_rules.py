"""A quarantine entry: its `test` and `expires` lines are written alone in a fixed shape (the
checks module reads the file by lines) and the test it names must be defined in a tracked file."""

from datetime import date

import pytest

from code_factory.settings.rules import ExceptionFacts, exceptions_problems
from code_factory.settings.rules.quarantine import definition_search

FILE = ".code-factory/exceptions.toml"
ENTRY = (
    '[[quarantine]]\ntest = "tests/test_a.py::test_flaky"\nreason = "r"\nticket = "CF-1"\n'
    "expires = 2999-12-31\n"
)


def run(text: str, *, exists: bool = True) -> list[tuple[int, str]]:
    facts = ExceptionFacts(
        tickets=frozenset({"CF-1"}),
        expiry_fails=True,
        tests={"tests/test_a.py::test_flaky": exists},
    )
    report = exceptions_problems(text, date(2026, 11, 2), facts)
    return [(p.line, p.message) for p in report.problems]


def test_a_well_written_entry_for_a_defined_test_passes() -> None:
    assert run(ENTRY) == []


def test_a_test_no_tracked_file_defines_is_named() -> None:
    assert run(ENTRY, exists=False) == [
        (2, "tests/test_a.py::test_flaky names no test in a tracked file")
    ]


def test_a_test_line_with_a_comment_or_indent_is_refused() -> None:
    commented = ENTRY.replace('flaky"', 'flaky" # why')
    indented = ENTRY.replace("test =", "  test =")
    shape = 'quarantine[0].test: not written as test = "<name>" alone on its line'
    assert run(commented) == [(2, shape)]
    assert run(indented) == [(2, shape)]


def test_an_expires_line_with_a_comment_is_refused() -> None:
    commented = ENTRY.replace("2999-12-31", "2999-12-31 # soon")
    assert run(commented) == [
        (5, "quarantine[0].expires: not written as expires = <date> alone on its line")
    ]


@pytest.mark.parametrize(
    ("test", "pattern", "paths"),
    [
        (
            "web/src/a.test.ts > Board > shows a card",
            "shows a card",
            ("web/src/a.test.ts", "*/web/src/a.test.ts"),
        ),
        (
            "tests/test_a.py::test_flaky",
            "def test_flaky(",
            ("tests/test_a.py", "*/tests/test_a.py"),
        ),
        (
            "tests/test_a.py::TestBoard::test_flaky[case-1]",
            "def test_flaky(",
            ("tests/test_a.py", "*/tests/test_a.py"),
        ),
        ("crate::suite::a_flaky_test", "fn a_flaky_test(", ("*.rs",)),
        ("binary crate::a::b_test", "fn b_test(", ("*.rs",)),
    ],
)
def test_where_a_named_test_is_defined(test: str, pattern: str, paths: tuple[str, ...]) -> None:
    assert definition_search(test) == (pattern, paths)
