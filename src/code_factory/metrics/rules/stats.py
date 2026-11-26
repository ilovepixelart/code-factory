"""Nearest-rank percentiles, medians and whole percents."""

import math
import statistics
from collections.abc import Sequence


def percentile(values: Sequence[float], q: float) -> float:
    """The nearest-rank percentile: the sorted value at position `max(ceil(q * n), 1)`.

    `statistics.median_low` equals `percentile(values, 0.5)`.
    """
    if not values:
        msg = "a percentile needs at least one value, and there are no values"
        raise ValueError(msg)
    ordered = sorted(values)
    return ordered[max(math.ceil(q * len(ordered)), 1) - 1]


def median(values: Sequence[float]) -> float | None:
    """`statistics.median`: the middle value or the mean of the two middle; None when empty."""
    return statistics.median(values) if values else None


def percent(part: int, whole: int) -> int:
    """`part` of `whole` as a whole percent, half up; 0 of nothing is 0."""
    return (part * 100 + whole // 2) // whole if whole else 0
