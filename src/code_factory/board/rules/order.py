"""The order of cards in a column."""

import re
from typing import Any

_RUNS = re.compile(r"(\d+)")

# Text at even slots, numbers at odd: `Any` because no type says that two keys compare.
type NaturalKey = tuple[Any, ...]


def natural_key(ticket_id: str) -> NaturalKey:
    """A sortable key: text and number runs alternate, starting and ending with a text run.

    Numbers compare by value (leading zeros ignored), and the empty run after a final number makes
    `CF-1` sort before `CF-1a` and `CF-1-2`. Even slots always hold text and odd slots numbers, so
    two keys never compare a string with an integer.
    """
    parts = _RUNS.split(ticket_id)
    return tuple(int(part) if index % 2 else str(part) for index, part in enumerate(parts))


def rank_key(rank: int, ticket_id: str) -> tuple[bool, int, NaturalKey]:
    """Rank 0 (unranked) sorts after every ranked card, then the natural order of the id."""
    return (rank == 0, rank, natural_key(ticket_id))
