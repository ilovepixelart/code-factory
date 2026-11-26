"""Stage times against the cycle, and what the panel shows of one ticket."""

import math
from collections.abc import Sequence

from code_factory.team.models import (
    Event,
    Median,
    Milestone,
    Peek,
    Stage,
    StageTimes,
    TicketFacts,
)
from code_factory.team.rules.rows import milestones

STAGES: tuple[Stage, ...] = ("first_commit", "pull_request", "gate_pass", "merged")
EVENTS = 5


def median(values: Sequence[float]) -> Median:
    """The nearest-rank median: the value at position `ceil(0.5 * n)` of the sorted values."""
    if not values:
        return Median(median=None, count=0)
    ordered = sorted(values)
    return Median(median=ordered[max(math.ceil(0.5 * len(ordered)), 1) - 1], count=len(ordered))


def _seconds(tickets: Sequence[TicketFacts], stage: int, since: float) -> list[float]:
    """Seconds from filing to a stage, for the tickets that reached it at or after `since`."""
    found: list[float] = []
    for ticket in tickets:
        reached = milestones(ticket)
        filed, at = reached[0], reached[stage]
        if filed is not None and at is not None and at >= since and at >= filed:
            found.append(at - filed)
    return found


def stage_times(
    tickets: Sequence[TicketFacts], today: float, since: float
) -> tuple[StageTimes, ...]:
    """Each stage's median seconds from filing, today and this cycle."""
    return tuple(
        StageTimes(
            stage=stage,
            today=median(_seconds(tickets, number, today)),
            cycle=median(_seconds(tickets, number, since)),
        )
        for number, stage in enumerate(STAGES, start=1)
    )


def peek(ticket: TicketFacts, stages: Sequence[StageTimes]) -> Peek:
    """A ticket's five milestones, each with the cycle's median, and its last five events."""
    reached = milestones(ticket)
    marks = [Milestone(stage="filed", at=reached[0], cycle=None)]
    marks.extend(
        Milestone(stage=times.stage, at=at, cycle=times.cycle.median)
        for times, at in zip(stages, reached[1:], strict=True)
    )
    events = tuple(Event(at=a.at, words=a.words) for a in reversed(ticket.activities[-EVENTS:]))
    return Peek(kind=ticket.kind, column=ticket.column, milestones=tuple(marks), events=events)
