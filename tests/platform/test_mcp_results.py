"""Paging a list a tool answers: whole items per page, a cursor that continues after the last."""

import pytest

from code_factory.platform.errors import BadRequestError
from code_factory.platform.mcp.results import PAGE_MAX, Page, page_after

ITEMS = ["a", "b", "c", "d", "e"]


def _key(item: str) -> str:
    return item


def test_a_page_holds_at_most_the_limit_and_names_where_the_next_begins() -> None:
    page = page_after(ITEMS, 2, None, _key)
    assert page == Page(items=["a", "b"], next_cursor="b")


def test_the_cursor_continues_after_the_item_it_names() -> None:
    assert page_after(ITEMS, 2, "b", _key) == Page(items=["c", "d"], next_cursor="d")


def test_the_last_page_has_no_cursor() -> None:
    assert page_after(ITEMS, 2, "d", _key) == Page(items=["e"], next_cursor=None)
    assert page_after(ITEMS, 5, None, _key) == Page(items=ITEMS, next_cursor=None)


def test_walking_the_cursors_visits_every_item_exactly_once() -> None:
    seen: list[str] = []
    cursor: str | None = None
    while True:
        page = page_after(ITEMS, 2, cursor, _key)
        seen += page.items
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == ITEMS


@pytest.mark.parametrize(("asked", "served"), [(0, 1), (-5, 1), (1000, PAGE_MAX)])
def test_a_limit_outside_one_to_the_maximum_is_clamped(asked: int, served: int) -> None:
    items = list(range(PAGE_MAX + 50))
    assert len(page_after(items, asked, None, str).items) == served


def test_a_cursor_for_an_item_that_is_gone_is_refused_with_what_to_do() -> None:
    with pytest.raises(BadRequestError, match="the cursor no longer matches the list"):
        page_after(ITEMS, 2, "zzz", _key)
