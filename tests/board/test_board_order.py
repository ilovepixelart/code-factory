"""Card order: rank first with 0 last, then the natural order of the id."""

import pytest

from code_factory.board.rules.order import natural_key, rank_key


@pytest.mark.parametrize(
    ("first", "second"),
    [("CF-2", "CF-10"), ("CF-1", "CF-1a"), ("CF-1", "CF-1-2"), ("AB-9", "CF-1")],
)
def test_natural_order_compares_numbers_by_value(first: str, second: str) -> None:
    assert natural_key(first) < natural_key(second)


def test_leading_zeros_do_not_change_the_order() -> None:
    assert natural_key("CF-007") == natural_key("CF-7")


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ((2, "CF-9"), (0, "CF-1")),
        ((1, "CF-5"), (2, "CF-1")),
        ((0, "CF-2"), (0, "CF-10")),
        ((3, "CF-2"), (3, "CF-10")),
    ],
)
def test_rank_zero_sorts_last_then_natural(first: tuple[int, str], second: tuple[int, str]) -> None:
    assert rank_key(*first) < rank_key(*second)
