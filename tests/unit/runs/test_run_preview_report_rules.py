import pytest

from code_factory.runs.rules.endings import ending_words
from code_factory.runs.rules.preview import preview_address
from code_factory.runs.rules.report import Report, report_problem, stored_tail


@pytest.mark.parametrize(
    ("board", "opened"),
    [
        ("http://localhost:4000", "http://127.0.0.1:4000/preview/5000"),
        ("http://127.0.0.1:4000", "http://localhost:4000/preview/5000"),
        ("http://[::1]:4000", "http://localhost:4000/preview/5000"),
        ("http://100.64.0.7:4000", "http://localhost:4000/preview/5000"),
        ("", "http://127.0.0.1:5000/"),
    ],
)
def test_a_preview_is_never_linked_on_the_boards_own_host(board: str, opened: str) -> None:
    assert preview_address(board, 5000) == opened


def report(**fields: object) -> Report:
    return Report(**({"stage": "build", "exit_code": 0} | fields))  # ty: ignore[invalid-argument-type]


def test_a_good_report_has_no_problem() -> None:
    assert report_problem(report(cost=1_000_000.0, model="m" * 200)) is None


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        ({"stage": "deploy"}, '"deploy" is not a column'),
        ({"log_tail": "x" * 65_537}, "the log tail holds over 65536 bytes"),
        ({"model": "m" * 201}, "the model holds over 200 bytes"),
        ({"cost": -0.01}, "the cost is not between 0 and 1000000"),
        ({"cost": 1_000_000.01}, "the cost is not between 0 and 1000000"),
    ],
)
def test_a_report_the_board_does_not_take_says_why(fields: dict[str, object], problem: str) -> None:
    assert report_problem(report(**fields)) == problem


def test_a_review_report_is_taken() -> None:
    assert report_problem(report(stage="review")) is None


def test_a_stored_tail_keeps_its_last_two_thousand_lines_marked() -> None:
    kept = stored_tail("\n".join(str(n) for n in range(2_500))).splitlines()
    assert len(kept) == 2_000
    assert kept[0] == "runner| 500"
    assert kept[-1] == "runner| 2499"


def test_a_stored_tail_drops_control_characters_but_a_tab() -> None:
    assert stored_tail("a\x1b[31mb\tc\x00") == "runner| a[31mb\tc\n"


@pytest.mark.parametrize(
    ("halted", "code", "words"),
    [
        ("", -15, "stopped, no reason recorded"),
        ("", 2, "exit 2"),
        ("stopped at its cap: 5000 tokens", 1, "token cap"),
        ("stopped at its cap: 90 seconds", 1, "time cap"),
        (
            "read enough: stopped at 40 tool calls with no change in its worktree",
            1,
            "no change after 40 tool calls",
        ),
        ("read enough: stopped at 12 tool calls repeating one call", 1, "one call repeated"),
        ("no progress at Build: same head twice", 1, "no progress at Build"),
    ],
)
def test_an_ending_is_worded_as_the_flow_page_counts_it(halted: str, code: int, words: str) -> None:
    assert ending_words(halted, code) == words
