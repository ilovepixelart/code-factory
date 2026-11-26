"""Percentiles, medians and the ranges the Flow page offers, worked by hand."""

import pytest

from code_factory.metrics.rules.stages import range_of
from code_factory.metrics.rules.stats import median, percent, percentile

DAY = 86400.0


def test_a_single_value_is_every_percentile() -> None:
    assert [percentile([180.0], q) for q in (0.01, 0.5, 0.95, 1.0)] == [180.0] * 4


def test_the_rank_rounds_up_so_p85_of_seven_values_is_the_sixth() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
    assert percentile(values, 0.85) == 60.0  # ceil(0.85 * 7) = 6


def test_the_median_rank_of_an_even_count_is_the_lower_middle() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.0
    assert percentile([1.0, 2.0, 3.0], 0.5) == 2.0


def test_percentile_sorts_its_input() -> None:
    assert percentile([30.0, 10.0, 20.0], 0.5) == 20.0


def test_a_percentile_of_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="no values"):
        percentile([], 0.5)


def test_the_median_of_nothing_is_none() -> None:
    assert median([]) is None


def test_the_median_of_an_even_count_is_the_mean_of_the_middle_two() -> None:
    assert median([4.0, 1.0, 3.0, 2.0]) == 2.5
    assert median([5.0, 1.0, 3.0]) == 3.0


def test_percent_rounds_half_up_and_is_zero_of_nothing() -> None:
    assert [percent(1, 8), percent(0, 0), percent(1, 2), percent(3, 3)] == [13, 0, 50, 100]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("24h", ("24h", DAY)),
        ("7d", ("7d", 7 * DAY)),
        ("30d", ("30d", 30 * DAY)),
        ("90d", ("90d", 90 * DAY)),
        ("1y", ("7d", 7 * DAY)),
        ("", ("7d", 7 * DAY)),
        ("24H", ("7d", 7 * DAY)),
    ],
)
def test_a_range_is_one_of_four_names_and_any_other_text_reads_as_seven_days(
    name: str, expected: tuple[str, float]
) -> None:
    assert range_of(name) == expected


def test_a_rank_with_a_fraction_always_rounds_up() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == 3.0  # ceil(2.5) = 3, not banker's 2
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.41) == 3.0  # ceil(2.05)
