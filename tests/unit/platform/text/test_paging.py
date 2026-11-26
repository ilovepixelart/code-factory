import pytest

from code_factory.platform.errors import BadRequestError
from code_factory.platform.text import (
    DEFAULT_SIZE,
    MAX_SIZE,
    PAGE_REFUSED,
    SIZE_REFUSED,
    Paged,
    Paging,
    page_of,
)

BIGGEST = 2**63 - 1


def test_the_refusal_sentences_and_bounds_are_the_documented_ones() -> None:
    assert PAGE_REFUSED == "page must be a whole number from 1"
    assert SIZE_REFUSED == "size must be a whole number from 1 to 100"
    assert (DEFAULT_SIZE, MAX_SIZE) == (50, 100)
    assert Paging(1, 50) == Paging.FIRST


def test_a_query_naming_neither_is_not_paged() -> None:
    assert Paging.from_query(None, None) is None


def test_a_missing_half_takes_its_default() -> None:
    assert Paging.from_query(None, "10") == Paging(1, 10)
    assert Paging.from_query("3", None) == Paging(3, 50)


@pytest.mark.parametrize("page", ["0", "01", "-1", "+2", "1.5", "", "abc", "1_0", "٣", " 1", "1 ",
                                  str(BIGGEST + 1)])  # fmt: skip
def test_a_page_that_is_not_a_whole_number_from_1_is_refused(page: str) -> None:
    with pytest.raises(BadRequestError) as refused:
        Paging.from_query(page, None)
    assert str(refused.value) == PAGE_REFUSED


@pytest.mark.parametrize("size", ["0", "010", "101", "x", "", "-1", "1_0", "٣", "9" * 20])
def test_a_size_that_is_not_a_whole_number_from_1_to_100_is_refused(size: str) -> None:
    with pytest.raises(BadRequestError) as refused:
        Paging.from_query(None, size)
    assert str(refused.value) == SIZE_REFUSED


def test_the_page_is_checked_before_the_size() -> None:
    with pytest.raises(BadRequestError) as refused:
        Paging.from_query("0", "0")
    assert str(refused.value) == PAGE_REFUSED


def test_the_bounds_are_accepted() -> None:
    assert Paging.from_query("1", "100") == Paging(1, 100)
    assert Paging.from_query(None, "1") == Paging(1, 1)
    assert Paging.from_query(str(BIGGEST), None) == Paging(BIGGEST, 50)


def test_within_clamps_to_the_last_page_and_an_empty_list_has_page_one() -> None:
    def paging(page: int) -> Paging:
        return Paging(page, 10)

    assert paging(9).within(23) == paging(3)
    assert paging(3).within(20) == paging(2)
    assert paging(3).within(21) == paging(3)
    assert paging(4).within(0) == paging(1)


def test_offset_is_the_rows_before_the_page() -> None:
    assert Paging(1, 10).offset == 0
    assert Paging(3, 10).offset == 20


def test_a_page_is_its_slice_and_past_the_last_the_last() -> None:
    rows = list(range(1, 248))
    assert page_of(rows, Paging(2, 10)).rows == list(range(11, 21))
    assert page_of(rows, Paging(25, 10)).rows == list(range(241, 248))
    past = page_of(rows, Paging(40, 10))
    assert (past.page, len(past.rows), past.total, past.size) == (25, 7, 247, 10)
    empty = page_of([], Paging(4, 10))
    assert (empty.page, empty.total, empty.rows) == (1, 0, [])


def test_map_changes_each_row_and_keeps_the_place() -> None:
    page = Paged(rows=[1, 2], total=9, page=2, size=2).map(lambda n: n * 10)
    assert page == Paged(rows=[10, 20], total=9, page=2, size=2)


def test_into_answer_sets_the_list_then_total_page_size() -> None:
    answer = Paged(rows=["a"], total=1, page=1, size=50).into_answer({"q": "x"}, "items")
    assert answer == {"q": "x", "items": ["a"], "total": 1, "page": 1, "size": 50}
    assert list(answer) == ["q", "items", "total", "page", "size"]


@pytest.mark.parametrize("digits", [5000, 20])
def test_an_enormous_number_is_refused_not_an_error(digits: int) -> None:
    with pytest.raises(BadRequestError) as refused:
        Paging.from_query("9" * digits, None)
    assert str(refused.value) == PAGE_REFUSED
    with pytest.raises(BadRequestError) as too_big:
        Paging.from_query(None, "9" * digits)
    assert str(too_big.value) == SIZE_REFUSED
