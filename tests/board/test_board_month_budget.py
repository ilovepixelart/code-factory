"""The month window and the day the monthly budget runs out."""

from datetime import UTC, datetime

import pytest

from code_factory.board.rules.budget import Lasts, On, Reached, month_bounds, month_budget, runout


def at(month: int, day: int, hour: int = 0, year: int = 2026) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


def test_the_window_is_this_utc_month() -> None:
    assert month_bounds(at(11, 15, 12)) == (at(11, 1), at(12, 1))


def test_the_last_instant_of_october_is_outside_novembers_window() -> None:
    start, _ = month_bounds(at(10, 31, 23))
    assert start == at(10, 1)


def test_december_wraps_to_january() -> None:
    assert month_bounds(at(12, 31)) == (at(12, 1), at(1, 1, year=2027))


@pytest.mark.parametrize(
    ("spent", "budget", "now", "expected"),
    [
        (21, 41, at(11, 11, 12), On("2026-11-21")),
        (21, 70, at(11, 11, 12), Lasts()),
        (45, 40, at(11, 11, 12), Reached()),
        (40, 40, at(11, 11, 12), Reached()),
        (39.9, 40, at(11, 30, 12), On("2026-11-30")),
        (39, 40, at(11, 30, 12), Lasts()),
        (30.4, 30.5, at(12, 31, 12), On("2026-12-31")),
        (30, 30.5, at(12, 31, 12), Lasts()),
        (20, 40, at(11, 16), Lasts()),
        (20, 39.99, at(11, 16), On("2026-11-30")),
        (0, 40, at(11, 16), Lasts()),
        (-0.0, 40, at(11, 16), Lasts()),
    ],
)
def test_the_runout_at_the_months_pace(
    spent: float, budget: float, now: datetime, expected: object
) -> None:
    assert runout(spent, budget, now) == expected


def test_the_month_budget_names_the_month_and_the_day() -> None:
    assert month_budget(21, 41, at(11, 11, 12)) == {
        "month": "2026-11",
        "spent": 21,
        "budget": 41,
        "runs_out": "2026-11-21",
        "reached": False,
    }


def test_a_reached_budget_has_no_day() -> None:
    assert month_budget(13, 12, at(11, 11, 12)) == {
        "month": "2026-11",
        "spent": 13,
        "budget": 12,
        "runs_out": None,
        "reached": True,
    }


def test_a_lasting_budget_has_no_day_and_is_not_reached() -> None:
    answer = month_budget(1, 12, at(11, 11, 12))
    assert answer is not None
    assert (answer["runs_out"], answer["reached"]) == (None, False)


def test_without_a_monthly_budget_there_is_no_answer() -> None:
    assert month_budget(5, None, at(11, 11)) is None


def test_a_tiny_spend_against_a_huge_budget_lasts_the_month() -> None:
    assert runout(0.000001, 10_000, at(11, 20)) == Lasts()
