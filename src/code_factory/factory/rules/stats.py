"""Median and the limit of a list."""

import statistics
from collections.abc import Sequence

from code_factory.platform.errors import BadRequestError

MAX_LIMIT = 50


def median(values: Sequence[float]) -> float | None:
    """The middle value, the mean of the middle pair when even; None for no values."""
    return float(statistics.median(values)) if values else None


def limit_of(raw: str | int | None, *, default: int) -> int:
    """A list limit from 1 to 50; `default` when none is given."""
    if raw is None:
        return default
    if isinstance(raw, str):
        try:
            value = int(raw) if raw.isascii() and raw.isdigit() else 0
        except ValueError:  # more digits than Python converts
            value = 0
    else:
        value = 0 if isinstance(raw, bool) else raw
    if not 1 <= value <= MAX_LIMIT:
        msg = f"limit must be a whole number from 1 to {MAX_LIMIT}"
        raise BadRequestError(msg)
    return value
