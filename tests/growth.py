"""How a piece of work grows with its input, measured so that load on the machine cancels out.

A fixed time budget fails when other work slows the machine; the ratio of two sizes measured back
to back does not. Four times the input takes about four times as long when the work is linear
and about sixteen times when it is quadratic, so `LINEAR_BOUND` separates the two.
"""

import time
from collections.abc import Callable

FACTOR = 4
LINEAR_BOUND = 8.0
REPEATS = 3
RESOLUTION_S = 1e-4  # below this the clock says nothing; the smaller size must take longer


def _best(work: Callable[[], object]) -> float:
    best = float("inf")
    for _ in range(REPEATS):  # the first run pays for warming up; load can slow any one run
        started = time.process_time()
        work()
        best = min(best, time.process_time() - started)
    return best


def growth(work: Callable[[int], object], size: int) -> float:
    """CPU time of `work(FACTOR * size)` over that of `work(size)`, best of three each."""
    small = _best(lambda: work(size))
    large = _best(lambda: work(FACTOR * size))
    return large / max(small, RESOLUTION_S)
