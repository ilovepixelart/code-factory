"""Minutes each ticket spent in each column."""

import math
from collections.abc import Sequence

from code_factory.metrics.models import ColumnTime, Transition
from code_factory.metrics.rules.stages import time_in_stages
from code_factory.metrics.rules.stats import percentile

COLUMNS = ("spec", "build", "review")
_Triple = tuple[float | None, float | None, float | None]


def minutes(seconds: float) -> int:
    """Seconds as whole minutes, the nearest, half up (`round` is banker's rounding)."""
    return math.floor(seconds / 60 + 0.5)


def column_times(
    tickets: Sequence[tuple[str, Sequence[Transition]]], since: float, now: float
) -> list[ColumnTime]:
    """Whole minutes in spec, build and review of each ticket that moved at or after `since`.

    A column never entered is None; the current column counts to `now`. Newest move first, then id.
    """
    moved: list[tuple[float, ColumnTime]] = []
    for ticket, timeline in tickets:
        if not timeline or timeline[-1].at < since:
            continue
        spent = dict(time_in_stages(timeline, now))
        spans = tuple(minutes(spent[c]) if c in spent else None for c in COLUMNS)
        last = timeline[-1]
        moved.append((last.at, ColumnTime(ticket=ticket, minutes=spans, now=last.stage)))
    moved.sort(key=lambda pair: (-pair[0], pair[1].ticket))
    return [row for _, row in moved]


def column_medians(rows: Sequence[ColumnTime]) -> _Triple:
    """The median minutes in each column over the tickets that entered it; None when none did."""
    medians: list[float | None] = []
    for n in range(len(COLUMNS)):
        spent = [float(row.minutes[n]) for row in rows if row.minutes[n] is not None]  # ty: ignore[invalid-argument-type]  # filtered
        medians.append(percentile(spent, 0.5) if spent else None)
    return medians[0], medians[1], medians[2]
