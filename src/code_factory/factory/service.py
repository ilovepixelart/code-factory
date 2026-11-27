"""The factory's use cases: bulk reads from five ports, then pure rules over what came back.

Reads go one after another: a provider may share one database connection with the next, and
each is a single bulk call. Nothing is stored; every answer is computed from the providers'
facts on each read.
"""

import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from code_factory.factory.models import (
    Dashboard,
    ExpensiveList,
    Improvements,
    MergedCost,
    OwnerTime,
    PullFact,
    RoleNoteOutcome,
    RunBreakdowns,
    RunCost,
    RunFact,
    Scorers,
    Series,
)
from code_factory.factory.ports import (
    CostPort,
    ImprovementPort,
    OwnerTimePort,
    PullsPort,
    RepairsPort,
    RoleNotesPort,
    RunsPort,
    ScorerPort,
)
from code_factory.factory.repository import OwnerTimeRepository
from code_factory.factory.rules.cohort import autonomy, cohort, is_merged
from code_factory.factory.rules.cost import (
    cost_summary,
    expensive,
    measurement_spend,
    merged_cost_summary,
    pr_cost,
)
from code_factory.factory.rules.cycle import cycle, cycle_summary, kickoffs
from code_factory.factory.rules.fixes import fix_outcomes
from code_factory.factory.rules.period import period
from code_factory.factory.rules.runs import run_breakdowns
from code_factory.factory.rules.scorers import scorer_views
from code_factory.factory.rules.series import series
from code_factory.factory.rules.stats import limit_of
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import NotFoundError, UnavailableError

EXPENSIVE_DEFAULT = 10
EXPENSIVE_ON_DASHBOARD = 5
IMPROVEMENTS_DEFAULT = 3

type Instant = str | float | None


@dataclass(frozen=True)
class FactoryPorts:
    """The five providers the factory reads from."""

    runs: RunsPort
    pulls: PullsPort
    costs: CostPort
    scorers: ScorerPort
    improvements: ImprovementPort
    repairs: RepairsPort | None = None
    role_notes: RoleNotesPort | None = None
    owner_time: OwnerTimePort | None = None


@dataclass(frozen=True)
class _Ledger:
    """Runs by ticket and what every run read cost."""

    by_ticket: dict[str, list[RunFact]]
    costs: dict[str, RunCost]


class OwnerTimeService:
    """Owner time is private to Factory's HTTP API and analytics."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def record(self, ticket: str, entry: OwnerTime) -> None:
        """Upsert the owner time recorded for one pull request."""
        async with self._uow() as session:
            await OwnerTimeRepository(session).record(ticket, entry)

    async def recorded(self, tickets: list[str]) -> dict[tuple[str, str], OwnerTime]:
        """Read every recorded owner entry of the named tickets in one query."""
        async with self._uow() as session:
            return await OwnerTimeRepository(session).recorded(tickets)


class FactoryService:
    """Factory output and model performance over a range."""

    def __init__(self, ports: FactoryPorts, now: Callable[[], float] = time.time) -> None:
        self._ports = ports
        self._now = now

    async def dashboard(self, from_: Instant, to: Instant) -> Dashboard:
        """Every figure of the factory page for the range."""
        span = period(from_, to, self._now())
        ports = self._ports
        runs = await ports.runs.runs(span.from_, span.to)
        pulls = await ports.pulls.in_range(span.from_, span.to)
        opened = [p for p in pulls if span.from_ <= p.opened_at < span.to]
        merged = [
            p for p in pulls if p.merged_at is not None and span.from_ <= p.merged_at < span.to
        ]
        scorers = await ports.scorers.cards(span.from_, span.to)
        improvements = await ports.improvements.newest(IMPROVEMENTS_DEFAULT)
        group = cohort(opened, merged, span.from_, span.to, span.now)
        merged_in_period = {p.url: p for p in merged if is_merged(p, span.now)}
        ledger = await self._ledger(
            [*group.members, *merged_in_period.values()] if ports.owner_time else group.members,
            runs,
        )
        costed = [
            pr_cost(p, ledger.by_ticket.get(p.ticket_id or "", []), ledger.costs, span.now)
            for p in group.members
        ]
        members_merged = [p for p in group.members if is_merged(p, span.now)]
        kickoff = kickoffs([r for rows in ledger.by_ticket.values() for r in rows])
        cycles = [cycle(p, kickoff.get(p.ticket_id or "")) for p in members_merged]
        tickets = sorted({p.ticket_id for p in group.members if p.ticket_id is not None})
        repairs = await ports.repairs.repair_requests(tickets) if ports.repairs and tickets else {}
        notes = (
            await ports.role_notes.role_note_outcomes(span.from_, span.to)
            if ports.role_notes
            else {}
        )
        return Dashboard(
            from_=span.from_,
            to=span.to,
            now=span.now,
            runs=run_breakdowns(runs, span.from_, span.to),
            prs=group.counts,
            series=series(group.members, span.from_, span.to, span.now),
            autonomy=autonomy(members_merged),
            cycle=cycle_summary(cycles),
            cost=cost_summary(costed, measurement_spend(runs, ledger.costs)),
            merged_cost=await self._merged_cost(merged_in_period, ledger, span.now),
            expensive=expensive(costed, EXPENSIVE_ON_DASHBOARD),
            scorers=scorer_views(scorers),
            improvements=improvements,
            fix_rounds=fix_outcomes(group.members, repairs, span.now),
            role_notes=[
                RoleNoteOutcome(role=role, notes=total, fixed=fixed)
                for role, (total, fixed) in notes.items()
            ],
        )

    async def pull_series(self, from_: Instant, to: Instant) -> Series:
        """Opening-cohort chart from Delivery, without loading the dashboard providers."""
        span = period(from_, to, self._now())
        opened = await self._ports.pulls.in_range(span.from_, span.to)
        return series(opened, span.from_, span.to, span.now)

    async def record_owner_time(self, ticket: str, entry: OwnerTime) -> None:
        """Replace the owner's active time for one merged pull request."""
        if self._ports.owner_time is None:
            msg = "Recording owner time is unavailable."
            raise UnavailableError(msg)
        if not await self._ports.pulls.known_merge(ticket, entry.pull_url):
            msg = "This ticket has no merged pull request with that URL."
            raise NotFoundError(msg)
        await self._ports.owner_time.record(ticket, entry)

    async def _merged_cost(
        self, merges: dict[str, PullFact], ledger: _Ledger, now: float
    ) -> MergedCost:
        owner_time = self._ports.owner_time
        tickets = sorted({p.ticket_id for p in merges.values() if p.ticket_id is not None})
        if owner_time is None or not tickets:
            return MergedCost(
                median=None, priced=0, owner_recorded=0, merged=len(merges), estimated=False
            )
        return merged_cost_summary(
            [
                pr_cost(p, ledger.by_ticket.get(p.ticket_id or "", []), ledger.costs, now)
                for p in merges.values()
            ],
            await owner_time.recorded(tickets),
        )

    async def runs(self, from_: Instant, to: Instant) -> RunBreakdowns:
        """The runs started in the range, counted five ways."""
        span = period(from_, to, self._now())
        return run_breakdowns(await self._ports.runs.runs(span.from_, span.to), span.from_, span.to)

    async def expensive(
        self, from_: Instant, to: Instant, limit: str | int | None
    ) -> ExpensiveList:
        """The most expensive pull requests of the range's cohort."""
        span = period(from_, to, self._now())
        count = limit_of(limit, default=EXPENSIVE_DEFAULT)
        opened = await self._ports.pulls.in_range(span.from_, span.to)
        members = cohort(opened, [], span.from_, span.to, span.now).members
        ledger = await self._ledger(members, [])
        costed = [
            pr_cost(p, ledger.by_ticket.get(p.ticket_id or "", []), ledger.costs, span.now)
            for p in members
        ]
        return ExpensiveList(prs=expensive(costed, count))

    async def scorers(self, from_: Instant, to: Instant) -> Scorers:
        """The scorer cards for the range."""
        span = period(from_, to, self._now())
        return scorer_views(await self._ports.scorers.cards(span.from_, span.to))

    async def improvements(self, limit: str | int | None) -> Improvements:
        """The newest self-improvement pull requests."""
        count = limit_of(limit, default=IMPROVEMENTS_DEFAULT)
        got = await self._ports.improvements.newest(count)
        return Improvements(available=got.available, items=got.items[:count])

    async def _ledger(self, members: Sequence[PullFact], runs: Sequence[RunFact]) -> _Ledger:
        """The members' tickets' runs and the cost of every run read, in one read each."""
        tickets = sorted({p.ticket_id for p in members if p.ticket_id is not None})
        ticket_runs = await self._ports.runs.for_tickets(tickets) if tickets else []
        by_ticket: dict[str, list[RunFact]] = defaultdict(list)
        for run in ticket_runs:
            if run.ticket_id is not None:
                by_ticket[run.ticket_id].append(run)
        ids = sorted({r.id for r in (*runs, *ticket_runs)})
        costs = await self._ports.costs.costs(ids) if ids else {}
        return _Ledger(by_ticket, costs)
