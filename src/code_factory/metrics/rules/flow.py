"""The Flow page: every field of `GET /api/flow` from merges, tickets, runs and branches."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from code_factory.metrics.models import (
    Autonomy,
    AutonomyCounts,
    Columns,
    Completion,
    CostStats,
    FlowPage,
    InFlightRow,
    LeadStats,
    MergedRow,
    MergeFact,
    RunFacts,
    TicketFlow,
)
from code_factory.metrics.rules.agents import agent_rows
from code_factory.metrics.rules.columns import column_medians, column_times
from code_factory.metrics.rules.stages import DAY, HOUR, range_of, timeline_of
from code_factory.metrics.rules.stats import percentile

STUCK_FLOOR = DAY  # stuck after a day while too few merges give a lead time to judge by
LEAD_SAMPLE = 5
Tickets = Mapping[tuple[str, str], TicketFlow]


@dataclass(frozen=True)
class InFlight:
    """A ticket in build or review on a branch, with when the branch was cut (None when unknown)."""

    repository: str
    ticket: TicketFlow
    cut: float | None


def _ticket_costs(runs: Sequence[RunFacts]) -> dict[tuple[str, str], tuple[float, bool]]:
    """What the runs of each ticket cost, and whether any of that is an estimate."""
    costs: dict[tuple[str, str], tuple[float, bool]] = {}
    for run in runs:
        if run.cost is not None:
            spent, estimated = costs.get((run.repository, run.ticket_id), (0.0, False))
            costs[(run.repository, run.ticket_id)] = (
                spent + run.cost,
                estimated or run.cost_estimated,
            )
    return costs


def _fixes(tickets: Tickets) -> dict[tuple[str, str], list[str]]:
    """For each ticket a ticket's `caused_by` names, the tickets naming it: the field only."""
    fixes: dict[tuple[str, str], set[str]] = {}
    for (repository, _), found in tickets.items():
        for cause in found.caused_by:
            fixes.setdefault((repository, cause), set()).add(found.id)
    return {key: sorted(ids) for key, ids in fixes.items()}


def _merged_row(
    merge: MergeFact,
    tickets: Tickets,
    costs: Mapping[tuple[str, str], tuple[float, bool]],
    fixes: Mapping[tuple[str, str], list[str]],
    web: str | None,
) -> MergedRow:
    key = (merge.repository, merge.ticket) if merge.ticket is not None else None
    known = tickets.get(key) if key else None
    spent = costs.get(key) if key else None
    filed = known.created_at.timestamp() if known is not None else None
    start = filed if filed is not None and filed <= merge.at else None
    return MergedRow(
        repository=merge.repository,
        pull=merge.pull,
        url=f"{web}/pull/{merge.pull}" if web is not None and merge.pull is not None else None,
        branch=merge.branch,
        ticket=merge.ticket,
        title=known.title if known is not None else "",
        at=merge.at,
        lead=max(merge.at - (merge.started if start is None else start), 0.0),
        from_="first_commit" if start is None else "filed",
        autonomy=merge.autonomy,
        cost=spent[0] if spent is not None else None,
        cost_estimated=spent[1] if spent is not None else None,
        reverted=merge.reverted,
        fixes=fixes.get(key, []) if key else [],
        checks=merge.checks,
    )


def _lead_stats(rows: Sequence[MergedRow]) -> tuple[LeadStats, float]:
    leads = [row.lead for row in rows if row.from_ == "filed"]
    p85 = percentile(leads, 0.85) if leads else None
    stats = LeadStats(
        median=percentile(leads, 0.5) if leads else None,
        p85=p85,
        p95=percentile(leads, 0.95) if leads else None,
        count=len(leads),
    )
    stuck_after = max(p85, HOUR) if p85 is not None and len(leads) >= LEAD_SAMPLE else STUCK_FLOOR
    return stats, stuck_after


def _cost_stats(rows: Sequence[MergedRow]) -> CostStats:
    tickets = [row for row in rows if row.ticket is not None]
    costs = [row.cost for row in tickets if row.cost is not None]
    return CostStats(
        median=percentile(costs, 0.5) if costs else None,
        estimated=any(row.cost_estimated for row in tickets),
        count=len(costs),
        of=len(tickets),
    )


def _autonomy_counts(rows: Sequence[MergedRow]) -> AutonomyCounts:
    count = {a: sum(row.autonomy == a for row in rows) for a in Autonomy}
    classed = count[Autonomy.AUTONOMOUS] + count[Autonomy.ASSISTED]
    return AutonomyCounts(
        share=count[Autonomy.AUTONOMOUS] / classed if classed else None,
        autonomous=count[Autonomy.AUTONOMOUS],
        assisted=count[Autonomy.ASSISTED],
        unknown=count[Autonomy.UNKNOWN],
    )


def _completion(
    merges: Sequence[MergeFact], build_starts: Mapping[str, Mapping[str, float]], now: float
) -> Completion:
    """Tickets whose build started in the window, and those merged at or after their first start."""
    started = sum(len(starts) for starts in build_starts.values())
    merged: set[tuple[str, str]] = set()
    for merge in merges:
        if merge.ticket is None or merge.at > now:
            continue
        start = build_starts.get(merge.repository, {}).get(merge.ticket)
        if start is not None and start <= merge.at:
            merged.add((merge.repository, merge.ticket))
    return Completion(started=started, merged=len(merged))


def _columns(merges: Sequence[MergeFact], tickets: Tickets, now: float) -> Columns:
    timelines = [
        (m.ticket, timeline_of(tickets[(m.repository, m.ticket)]))
        for m in merges
        if m.ticket is not None and (m.repository, m.ticket) in tickets
    ]
    spec, build, review = column_medians(column_times(timelines, 0.0, now))
    return Columns(spec=spec, build=build, review=review)


def _stuck(in_flight: Sequence[InFlight], now: float, stuck_after: float) -> list[InFlightRow]:
    rows = [
        (
            None if flight.cut is None else max(now - flight.cut, 0.0),
            InFlightRow(
                repository=flight.repository,
                id=flight.ticket.id,
                title=flight.ticket.title,
                stage=flight.ticket.stage,
                age=None if flight.cut is None else max(now - flight.cut, 0.0),
                needs=flight.ticket.needs,
            ),
        )
        for flight in in_flight
    ]
    rows.sort(key=lambda pair: -(pair[0] or 0.0))
    return [row for age, row in rows if age is not None and age > stuck_after]


def assemble_flow(  # noqa: PLR0913  # the page's facts, all keyword
    *,
    range_name: str,
    now: float,
    merges: Sequence[MergeFact],
    tickets: Tickets,
    runs: Sequence[RunFacts],
    build_starts: Mapping[str, Mapping[str, float]],
    in_flight: Sequence[InFlight],
    web: Mapping[str, str | None],
) -> FlowPage:
    """The Flow page for the window `range_name` names, ending at `now`.

    `merges` are the ledger rows of the window; `tickets` the facts of their tickets and of any
    ticket that may name one as its cause, by (repository, id); `build_starts` the first Build run
    start of each ticket in the window, by repository; `in_flight` the tickets in build or review
    on a branch (archived ones are not passed). Lead is from the ticket's filing when it is known
    and not after the merge, else from the branch's first commit.
    """
    name, length = range_of(range_name)
    costs, fixes = _ticket_costs(runs), _fixes(tickets)
    ordered = sorted(merges, key=lambda m: (-m.at, m.repository, m.commit))
    rows = [_merged_row(m, tickets, costs, fixes, web.get(m.repository)) for m in ordered]
    lead, stuck_after = _lead_stats(rows)
    return FlowPage(
        range=name,
        since=now - length,
        now=now,
        merged=rows,
        lead=lead,
        completion=_completion(ordered, build_starts, now),
        cost=_cost_stats(rows),
        autonomy=_autonomy_counts(rows),
        columns=_columns(ordered, tickets, now),
        in_flight=len(in_flight),
        stuck_after=stuck_after,
        stuck=_stuck(in_flight, now, stuck_after),
        agents=agent_rows(runs, now - length),
    )
