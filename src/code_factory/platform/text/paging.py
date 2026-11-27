"""One page of a list a read answers: the page a query names and the slice it holds."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from code_factory.platform.errors import BadRequestError

DEFAULT_SIZE = 50
MAX_SIZE = 100
PAGE_REFUSED = "page must be a whole number from 1"
SIZE_REFUSED = "size must be a whole number from 1 to 100"

_BIGGEST = 2**63 - 1
# ASCII digits with no sign, padding or underscore: `int()` accepts all of those, and `\d`
# without `re.ASCII` the digits of every script.
_WHOLE = re.compile(r"[1-9]\d*", re.ASCII)


def _whole(text: str) -> int | None:
    if len(text) > len(str(_BIGGEST)) or _WHOLE.fullmatch(text) is None:
        return None
    number = int(text)
    return number if number <= _BIGGEST else None


@dataclass(frozen=True, slots=True)
class Paging:
    """The page a query asks for."""

    page: int
    size: int

    FIRST: ClassVar[Paging]

    @property
    def offset(self) -> int:
        """The rows before this page."""
        return (self.page - 1) * self.size

    def within(self, total: int) -> Paging:
        """The page of `total` rows this one names, the last when it is past it."""
        last = max(1, -(-total // self.size))
        return Paging(min(self.page, last), self.size)

    @classmethod
    def from_query(cls, page: str | None, size: str | None) -> Paging | None:
        """The page a query names: None when it names neither, a missing half its default.

        Routes declare `page` and `size` as `str | None`: an `int` annotation would answer 422.

        Raises:
            BadRequestError: `page` is not a whole number from 1, or `size` not one from 1 to
                100. The page is checked first.
        """
        if page is None and size is None:
            return None
        number = 1 if page is None else _whole(page)
        if number is None:
            raise BadRequestError(PAGE_REFUSED)
        length = DEFAULT_SIZE if size is None else _whole(size)
        if length is None or length > MAX_SIZE:
            raise BadRequestError(SIZE_REFUSED)
        return cls(number, length)


Paging.FIRST = Paging(1, DEFAULT_SIZE)


@dataclass(frozen=True, slots=True)
class Paged[T]:
    """One page of rows and where it sits in the whole."""

    rows: list[T]
    total: int
    page: int
    size: int

    def map[U](self, change: Callable[[T], U]) -> Paged[U]:
        """The same page with each row made into another."""
        return Paged([change(row) for row in self.rows], self.total, self.page, self.size)

    def into_answer(self, answer: dict[str, object], key: str) -> dict[str, object]:
        """Set the rows under `key`, then `total`, `page` and `size`, in that order."""
        answer[key] = self.rows
        answer["total"] = self.total
        answer["page"] = self.page
        answer["size"] = self.size
        return answer


def page_of[T](rows: list[T], paging: Paging) -> Paged[T]:
    """The page of an in-memory, filtered and sorted list: past the last is the last."""
    placed = paging.within(len(rows))
    start = placed.offset
    return Paged(rows[start : start + paging.size], len(rows), placed.page, paging.size)
