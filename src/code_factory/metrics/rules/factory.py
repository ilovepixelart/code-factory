"""The factory view: how each agent and model's merged work held up."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from code_factory.metrics.models import Yield
from code_factory.metrics.rules.stats import median


@dataclass(frozen=True)
class FactoryRow:
    """One merged ticket: when it came in to when it merged, and the tickets that escaped it."""

    repository: str
    ticket: str
    intake_to_merge: float
    escaped: tuple[str, ...]


@dataclass(frozen=True)
class BoardRun:
    """One run, for `yields`: who ran, on what, at which stage, and what it reported costing."""

    repository: str
    ticket: str
    agent: str
    model: str
    stage: str
    cost: float | None
    unfinished: bool


@dataclass
class _Tally:
    runs: int = 0
    unfinished: int = 0
    merged: int = 0
    held: int = 0
    end_to_end: int = 0
    cost: float | None = None


def yields(rows: Sequence[FactoryRow], worked: Sequence[BoardRun]) -> list[Yield]:
    """The yield of each (agent, model) of `worked`, an entry even with no merged ticket.

    A ticket counts once for each setup that ran on it, and its cost is not split: each setup
    counts only its own runs. Ordered by agent, then model.
    """
    tallies: dict[tuple[str, str], _Tally] = defaultdict(_Tally)
    intakes: dict[tuple[str, str], list[float]] = defaultdict(list)
    for run in worked:
        tally = tallies[(run.agent, run.model)]
        tally.runs += 1
        tally.unfinished += run.unfinished
    by_ticket: dict[tuple[str, str], list[BoardRun]] = defaultdict(list)
    for run in worked:
        by_ticket[(run.repository, run.ticket)].append(run)
    for row in rows:
        setups: dict[tuple[str, str], list[BoardRun]] = defaultdict(list)
        for run in by_ticket[(row.repository, row.ticket)]:
            setups[(run.agent, run.model)].append(run)
        for key, runs in setups.items():
            tally = tallies[key]
            tally.merged += 1
            tally.held += not row.escaped
            stages = {run.stage for run in runs}
            tally.end_to_end += {"spec", "build"} <= stages
            for cost in (run.cost for run in runs if run.cost is not None):
                tally.cost = (tally.cost or 0.0) + cost
            intakes[key].append(row.intake_to_merge)
    return [
        Yield(
            agent=agent,
            model=model,
            runs=tally.runs,
            unfinished=tally.unfinished,
            merged=tally.merged,
            held=tally.held,
            end_to_end=tally.end_to_end,
            median_intake_to_merge=median(intakes[(agent, model)]),
            cost=tally.cost,
        )
        for (agent, model), tally in sorted(tallies.items())
    ]
