"""F10 pull requests opened and merged per day or per week."""

import math
from collections import defaultdict
from collections.abc import Sequence

from code_factory.factory.models import PullFact, Series, SeriesPoint
from code_factory.factory.rules.cohort import is_merged

DAY_S = 86400.0
WEEK_S = 7 * DAY_S
DAILY_UP_TO_S = 31 * DAY_S
MONDAY_OFFSET_S = 4 * DAY_S  # 1970-01-01 was a Thursday


def _bucket_start(instant: float, step: float, offset: float) -> float:
    return offset + math.floor((instant - offset) / step) * step


def series(pulls: Sequence[PullFact], since: float, until: float, now: float) -> Series:
    """One point per bucket, from the one holding `since` to the one holding `until` (exclusive).

    A bucket is a UTC day for a range of at most 31 days, else a week starting Monday. A point
    counts the pull requests opened in the bucket inside the range, and those that merged.
    """
    weekly = until - since > DAILY_UP_TO_S
    step, offset = (WEEK_S, MONDAY_OFFSET_S) if weekly else (DAY_S, 0.0)
    counts: dict[float, list[int]] = defaultdict(lambda: [0, 0])
    for pull in pulls:
        if since <= pull.opened_at < until:
            cell = counts[_bucket_start(pull.opened_at, step, offset)]
            cell[0] += 1
            cell[1] += is_merged(pull, now)
    first = _bucket_start(since, step, offset)
    end = _bucket_start(until, step, offset)
    last = end - step if end == until else end  # a bucket starting at `until` is outside the range
    starts = [first + i * step for i in range(round((last - first) / step) + 1)]
    points = [SeriesPoint(start=s, opened=counts[s][0], merged=counts[s][1]) for s in starts]
    return Series(bucket="week" if weekly else "day", points=points)
