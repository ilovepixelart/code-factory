"""The month's spend against the monthly budget, and the day it runs out at the month's pace."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class Reached:
    """The month's spend has reached its budget."""


@dataclass(frozen=True)
class Lasts:
    """The budget lasts the month at this pace."""


@dataclass(frozen=True)
class On:
    """The budget runs out on this UTC day (`YYYY-MM-DD`)."""

    day: str


MONTHS = 12


type Runout = Reached | Lasts | On


def month_bounds(now: datetime) -> tuple[datetime, datetime]:
    """The first instants of this UTC month and of the next."""
    moment = now.astimezone(UTC)
    start = datetime(moment.year, moment.month, 1, tzinfo=UTC)
    year, month = (
        (moment.year + 1, 1) if moment.month == MONTHS else (moment.year, moment.month + 1)
    )
    return start, datetime(year, month, 1, tzinfo=UTC)


def runout(spent: float, budget: float, now: datetime) -> Runout:
    """Whether the budget is spent, and when it runs out at the pace so far.

    The pace is the spend over the time elapsed in the month; the day is given only when it falls
    before the next month starts.
    """
    if spent >= budget:
        return Reached()
    if spent <= 0:
        return Lasts()
    start, following = month_bounds(now)
    elapsed = (now - start).total_seconds()
    until = elapsed * budget / spent
    if until >= (following - start).total_seconds():
        return Lasts()
    return On((start + timedelta(seconds=until)).date().isoformat())


def month_budget(spent: float, budget: float | None, now: datetime) -> dict[str, Any] | None:
    """The page's month budget: the month, its spend, the budget, the day it runs out."""
    if budget is None:
        return None
    projected = runout(spent, budget, now)
    return {
        "month": now.astimezone(UTC).strftime("%Y-%m"),
        "spent": spent,
        "budget": budget,
        "runs_out": projected.day if isinstance(projected, On) else None,
        "reached": isinstance(projected, Reached),
    }
