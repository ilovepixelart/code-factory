"""Stage timelines and what they say: time in each stage, weeks and days finished, the forecast."""

import random
from collections.abc import Sequence
from datetime import UTC, datetime

from code_factory.metrics.models import TicketFlow, Transition
from code_factory.metrics.rules.stats import percentile

DAY = 86400.0
HOUR = 3600.0
RANGES = {"24h": DAY, "7d": 7 * DAY, "30d": 30 * DAY, "90d": 90 * DAY}
DEFAULT_RANGE = "7d"
STAGES = ("spec", "build", "review", "merged")
FIRST_STAGE = "spec"
WEEKS = 8
DAYS = 56
TRIALS = 1000
SEED = 1
LONGEST_FORECAST = 3650
_DONE = STAGES.index("review")
_THURSDAY = 3  # 1970-01-01, day 0, is a Thursday; Monday is 0


def range_of(name: str) -> tuple[str, float]:
    """The range `name` names and its length in seconds; any other text reads as seven days."""
    chosen = name if name in RANGES else DEFAULT_RANGE
    return chosen, RANGES[chosen]


def stage_index(stage: str) -> int:
    """Where a stage sits in the board's order; an unknown one sorts after every stage."""
    return STAGES.index(stage) if stage in STAGES else len(STAGES)


def stage_timeline(
    created_at: float, first_stage: str, moves: Sequence[tuple[float, str]]
) -> list[Transition]:
    """The filing and then each move, oldest first.

    A move to the stage already current adds nothing, and moves sharing one instant are one: the
    last wins.
    """
    timeline = [Transition(at=created_at, stage=first_stage)]
    for at, stage in moves:
        if timeline[-1].at == at:
            timeline.pop()
        if timeline and timeline[-1].stage == stage:
            continue
        timeline.append(Transition(at=at, stage=stage))
    return timeline


def timeline_of(ticket: TicketFlow) -> list[Transition]:
    """A ticket's timeline: created in the first stage, then its recorded moves."""
    moves = [(move.at.timestamp(), move.to) for move in ticket.moves]
    return stage_timeline(ticket.created_at.timestamp(), FIRST_STAGE, moves)


def time_in_stages(timeline: Sequence[Transition], now: float) -> list[tuple[str, float]]:
    """Seconds in each stage in the order first entered, the last up to `now`; never negative."""
    spent: dict[str, float] = {}
    for n, current in enumerate(timeline):
        end = timeline[n + 1].at if n + 1 < len(timeline) else now
        spent[current.stage] = spent.get(current.stage, 0.0) + max(end - current.at, 0.0)
    return list(spent.items())


def reached_done(timeline: Sequence[Transition]) -> float | None:
    """When the ticket first reached review or a later stage."""
    return next((t.at for t in timeline if stage_index(t.stage) >= _DONE), None)


def start_seen(timeline: Sequence[Transition]) -> bool:
    """Whether the timeline begins before review: otherwise it says when the board first saw it."""
    return bool(timeline) and stage_index(timeline[0].stage) < _DONE


def measured_done(timeline: Sequence[Transition]) -> float | None:
    """When a ticket whose start was seen first reached review or later."""
    return reached_done(timeline) if start_seen(timeline) else None


def _day_number(instant: float) -> int:
    return int(instant // DAY)


def _monday(day: int) -> int:
    return day - (day + _THURSDAY) % 7


def throughput(
    timelines: Sequence[Sequence[Transition]], now: float, weeks: int = WEEKS
) -> list[int]:
    """Tickets whose measured done falls in each of the last `weeks` UTC weeks, oldest first.

    A week starts on Monday. An instant after `now` or older than the weeks is left out.
    """
    counts = [0] * weeks
    this_week = _monday(_day_number(now))
    for timeline in timelines:
        done = measured_done(timeline)
        if done is None or done > now:
            continue
        back = (this_week - _monday(_day_number(done))) // 7
        if back < weeks:
            counts[weeks - 1 - back] += 1
    return counts


def daily_counts(
    timelines: Sequence[Sequence[Transition]], now: float, days: int = DAYS
) -> list[int]:
    """The same count per UTC day, oldest first, the last the day of `now`."""
    counts = [0] * days
    today = _day_number(now)
    for timeline in timelines:
        done = measured_done(timeline)
        if done is None or done > now:
            continue
        back = today - _day_number(done)
        if back < days:
            counts[days - 1 - back] += 1
    return counts


def forecast(sample: Sequence[int], open_tickets: int) -> tuple[int, int] | None:
    """In how many days the open tickets are done at 50 and 85 percent likelihood.

    Each of 1000 trials draws a day's count from `sample` with `random.Random(1)` until done or
    3650 days. Nothing open is done today; a sample with no positive value says nothing (None).
    """
    if open_tickets == 0:
        return (0, 0)
    if not any(n > 0 for n in sample):
        return None
    rng = random.Random(SEED)  # noqa: S311  # a seeded draw for a reproducible forecast
    durations: list[float] = []
    for _ in range(TRIALS):
        done = days = 0
        while done < open_tickets and days < LONGEST_FORECAST:
            done += sample[rng.randrange(len(sample))]
            days += 1
        durations.append(float(days))
    return int(percentile(durations, 0.5)), int(percentile(durations, 0.85))


def utc_stamp(moment: float) -> str:
    """`2026-10-05T00:00:00Z` for an epoch time, in whole seconds."""
    return datetime.fromtimestamp(moment, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
