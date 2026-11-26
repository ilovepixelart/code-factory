"""What list tools answer: a page of whole items and where the next page begins."""

from collections.abc import Callable, Sequence
from typing import Annotated

from pydantic import BaseModel, Field

from code_factory.platform.errors import BadRequestError

PAGE_MAX = 100  # items a page may hold
# A list tool's page size: the schema carries the bound, so a call outside it is refused before
# the tool runs instead of being cut silently.
PageLimit = Annotated[int, Field(ge=1, le=PAGE_MAX, description=f"Page size, 1 to {PAGE_MAX}.")]


class Page[T](BaseModel):
    """Items in order; `next_cursor` goes back in as `cursor` for the following page."""

    items: list[T]
    next_cursor: str | None = None


def page_after[T](
    items: Sequence[T], limit: int, cursor: str | None, key: Callable[[T], str]
) -> Page[T]:
    """The `limit` items after the one whose key is `cursor` (from the start when `None`).

    A page ends between items. A cursor whose item left the list is refused rather than guessed.
    """
    size = min(max(limit, 1), PAGE_MAX)
    start = 0
    if cursor is not None:
        keys = [key(item) for item in items]
        if cursor not in keys:
            msg = "the cursor no longer matches the list; call again without a cursor"
            raise BadRequestError(msg)
        start = keys.index(cursor) + 1
    chosen = list(items[start : start + size])
    more = start + size < len(items)
    return Page(items=chosen, next_cursor=key(chosen[-1]) if more and chosen else None)
