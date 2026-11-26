"""F2 median, F12's limit and F3 size, with the spec's hand-worked values."""

import pytest

from code_factory.factory.models import Size
from code_factory.factory.rules.cost import size_of
from code_factory.factory.rules.stats import limit_of, median
from code_factory.platform.errors import BadRequestError


def test_the_median_of_nothing_is_none() -> None:
    assert median([]) is None


def test_the_median_of_one_value_is_that_value() -> None:
    assert median([7.0]) == 7.0


def test_the_median_of_an_even_count_is_the_mean_of_the_middle_pair() -> None:
    assert median([1.5, 2, 2, 2, 5, 10]) == 2.0


def test_the_median_of_unsorted_input_is_taken_after_sorting() -> None:
    assert median([10, 1.5, 2, 5, 2, 1.5]) == 2.0


def test_the_cost_list_of_the_fixture_has_median_1_75_not_the_mean() -> None:
    values = [1.5, 1.5, 1.5, 2.0, 5.0, 10.0]
    assert (median(values), sum(values) / len(values)) == (1.75, pytest.approx(3.583, abs=1e-3))


@pytest.mark.parametrize(
    ("lines", "size"),
    [
        (0, Size.S), (99, Size.S), (100, Size.M), (499, Size.M), (500, Size.L), (999, Size.L),
        (1000, Size.XL), (123456, Size.XL), (None, Size.UNKNOWN), (-1, Size.UNKNOWN),
    ],
)  # fmt: skip
def test_size_is_the_lower_bound_of_the_larger_class(lines: int | None, size: Size) -> None:
    assert size_of(lines) == size


@pytest.mark.parametrize(
    ("raw", "expected"), [(None, 10), ("1", 1), ("50", 50), (7, 7), ("007", 7)]
)
def test_a_limit_from_one_to_fifty_is_accepted(raw: str | int | None, expected: int) -> None:
    assert limit_of(raw, default=10) == expected


def test_a_limit_with_thousands_of_digits_is_refused_not_a_crash() -> None:
    with pytest.raises(BadRequestError, match=r"^limit must be a whole number from 1 to 50$"):
        limit_of("9" * 5000, default=10)


@pytest.mark.parametrize(
    "raw", ["0", "51", "-1", "abc", "", "5.0", "1e1", " 5", "\u0665", 0, 51, True]
)
def test_any_other_limit_is_refused_with_the_one_sentence(raw: str | int) -> None:
    with pytest.raises(BadRequestError, match=r"^limit must be a whole number from 1 to 50$"):
        limit_of(raw, default=10)
