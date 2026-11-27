"""F5 the cost of a pull request, F6 of a cohort, F12 the most expensive, and F3 size."""

import math
from collections.abc import Mapping, Sequence

from code_factory.factory.models import (
    Component,
    ComponentCost,
    CostSummary,
    ExpensivePr,
    MergedCost,
    OwnerTime,
    PrCost,
    PullFact,
    RunCost,
    RunFact,
    Size,
    SizeCost,
)
from code_factory.factory.rules.cohort import is_merged, state_at
from code_factory.factory.rules.stats import median

SIZE_S_UNDER = 100
SIZE_M_UNDER = 500
SIZE_L_UNDER = 1000
BOARD = "board"
_STAGE_COMPONENT = {
    "spec": Component.SPEC,
    "build": Component.BUILD,
    "review": Component.REVIEW,
}
_SIZES = (Size.S, Size.M, Size.L, Size.XL)


def size_of(lines: int | None) -> Size:
    """Size by changed lines: under 100 S, 100 to 499 M, 500 to 999 L, 1000 and up XL."""
    if lines is None or lines < 0:
        return Size.UNKNOWN
    if lines < SIZE_S_UNDER:
        return Size.S
    if lines < SIZE_M_UNDER:
        return Size.M
    return Size.L if lines < SIZE_L_UNDER else Size.XL


def pr_cost(
    pull: PullFact, runs: Sequence[RunFact], costs: Mapping[str, RunCost], now: float
) -> PrCost:
    """What the ticket's runs started before this pull request ended cost, split evenly.

    Only board runs count; measurement runs are the dashboard's measurement spend. The pull
    request ends at its merge, else at `now`. The split divides by the ticket's number
    of pull requests (below 1 reads as 1). `complete` is False when a run in scope has no cost.
    """
    end = pull.merged_at if pull.merged_at is not None and is_merged(pull, now) else now
    scoped = [
        run
        for run in runs
        if run.source == BOARD
        and pull.ticket_id is not None
        and run.ticket_id == pull.ticket_id
        and run.started_at < end
    ]
    share = max(pull.ticket_pulls, 1)
    sums: dict[Component, list[float]] = {}
    estimated = False
    for run in scoped:
        known = costs.get(run.id)
        if known is None or known.cost is None:
            continue
        component = _STAGE_COMPONENT.get(run.stage, Component.OTHER)
        sums.setdefault(component, []).append(known.cost)
        estimated = estimated or known.estimated
    priced = sum(len(values) for values in sums.values())
    return PrCost(
        pull=pull,
        state=state_at(pull, now),
        cost=math.fsum(v for values in sums.values() for v in values) / share if sums else None,
        complete=priced == len(scoped),
        estimated=estimated,
        runs=len(scoped),
        by_component={c: math.fsum(values) / share for c, values in sums.items()},
    )


def _component_costs(priced: Sequence[PrCost]) -> list[ComponentCost]:
    rows = []
    for component in Component:
        values = [c.by_component.get(component, 0.0) for c in priced]
        rows.append(
            ComponentCost(component=component, median=median(values), total=math.fsum(values))
        )
    return rows


def _size_costs(costed: Sequence[PrCost]) -> list[SizeCost]:
    sizes = [size_of(c.pull.changed_lines) for c in costed]
    shown = [*_SIZES, *([Size.UNKNOWN] if Size.UNKNOWN in sizes else [])]
    rows = []
    for size in shown:
        members = [c for c, s in zip(costed, sizes, strict=True) if s == size]
        values = [c.cost for c in members if c.cost is not None]
        rows.append(SizeCost(size=size, median=median(values), priced=len(values), of=len(members)))
    return rows


def cost_summary(costed: Sequence[PrCost], measurement: float) -> CostSummary:
    """Median cost per priced pull request, by component and by size; `measurement` is carried."""
    priced = [c for c in costed if c.cost is not None]
    return CostSummary(
        median=median([c.cost for c in priced if c.cost is not None]),
        priced=len(priced),
        of=len(costed),
        estimated=any(c.estimated for c in priced),
        measurement=measurement,
        by_component=_component_costs(priced),
        by_size=_size_costs(costed),
    )


def merged_cost_summary(
    costed: Sequence[PrCost], recorded: Mapping[tuple[str, str], OwnerTime]
) -> MergedCost:
    """Combine measured owner time with complete run costs, counting missing inputs."""
    totals = []
    owner_recorded = 0
    estimated = False
    for cost in costed:
        owner = recorded.get((cost.pull.ticket_id or "", cost.pull.url))
        if owner is None:
            continue
        owner_recorded += 1
        if cost.cost is None or not cost.complete:
            continue
        totals.append(cost.cost + owner.active_minutes / 60 * owner.hourly_rate_usd)
        estimated = estimated or cost.estimated
    return MergedCost(
        median=median(totals),
        priced=len(totals),
        owner_recorded=owner_recorded,
        merged=len(costed),
        estimated=estimated,
    )


def measurement_spend(runs: Sequence[RunFact], costs: Mapping[str, RunCost]) -> float:
    """What runs that are not board work (judges, evals, benchmarks) cost, priced ones only."""
    return math.fsum(
        known.cost
        for run in runs
        if run.source != BOARD
        and (known := costs.get(run.id)) is not None
        and known.cost is not None
    )


def expensive(costed: Sequence[PrCost], limit: int) -> list[ExpensivePr]:
    """The priced pull requests, dearest first, equal costs newest opened first, then by url."""
    priced = [c for c in costed if c.cost is not None]
    priced.sort(key=lambda c: (-(c.cost or 0.0), -c.pull.opened_at, c.pull.url))
    return [
        ExpensivePr(
            url=c.pull.url,
            repository=c.pull.repository,
            number=c.pull.number,
            ticket=c.pull.ticket_id,
            title=c.pull.title,
            state=c.state,
            opened_at=c.pull.opened_at,
            cost=c.cost or 0.0,
            cost_complete=c.complete,
            estimated=c.estimated,
            changed_lines=c.pull.changed_lines,
            size=size_of(c.pull.changed_lines),
            runs=c.runs,
        )
        for c in priced[:limit]
    ]
