"""The reports without a page: gate step times, the `times` report, throughput, forecast, yields."""

from collections.abc import Sequence
from datetime import datetime

from code_factory.metrics.models import (
    Forecast,
    StageMove,
    StepTime,
    TicketFlow,
    TimesReport,
    TrackedRepo,
    Yield,
)
from code_factory.metrics.repository import MetricsRepository
from code_factory.metrics.rules.columns import column_times
from code_factory.metrics.rules.factory import BoardRun, FactoryRow, yields
from code_factory.metrics.rules.gates import (
    columns_table,
    revert_line,
    steps_table,
    summarize_steps,
    window_runs,
)
from code_factory.metrics.rules.stages import (
    daily_counts,
    forecast,
    stage_index,
    throughput,
    timeline_of,
    utc_stamp,
)
from code_factory.metrics.service.deps import DAY, Deps, instant
from code_factory.platform.errors import BadRequestError

NO_RUNS = "no gate run has recorded step times yet\n"
YIELD_LOOKBACK_S = 90 * DAY


def check_last(last: int | None) -> None:
    """Refuse a window of fewer than one run."""
    if last is not None and last < 1:
        msg = "last must be at least 1: it is how many recent gate runs to read"
        raise BadRequestError(msg)


async def timelines_of(deps: Deps, repos: list[TrackedRepo]) -> list[tuple[str, TicketFlow]]:
    """Every ticket of the repositories, archived included, with its repository's name."""
    found: list[tuple[str, TicketFlow]] = []
    for repo in repos:
        found.extend((repo.name, t) for t in await deps.ports.tickets.flow_facts(repo.name))
    return found


async def step_times(deps: Deps, last: int | None) -> list[StepTime]:
    """Each gate step over the newest `last` recorded runs (all of them when None)."""
    check_last(last)
    runs = await deps.ports.checks.step_runs(last)
    return summarize_steps(runs, last if last is not None else len(runs))


async def times_report(deps: Deps, last: int, repository: str | None) -> TimesReport:
    """The step table, then the minutes per column and the reverts since the oldest run read."""
    check_last(last)
    repos = await deps.repositories(repository)
    window = window_runs(await deps.ports.checks.step_runs(last, repository=repository), last)
    if not window:
        return TimesReport(steps=[], since=None, columns=[], merges=0, reverted=0, text=NO_RUNS)
    since = window[-1].at.timestamp()
    stamp = utc_stamp(since)
    tickets = [(t.id, timeline_of(t)) for _, t in await timelines_of(deps, repos)]
    columns = column_times(tickets, since, deps.seconds())
    async with deps.uow() as session:
        merged = await MetricsRepository(session).merges_since(since, [r.name for r in repos])
    reverted = sum(m.reverted for m in merged)
    steps = summarize_steps(window, last)
    text = steps_table(steps)
    if columns:
        text += "\n" + columns_table(columns, stamp)
    if merged:
        text += "\n" + revert_line(len(merged), reverted, stamp)
    return TimesReport(
        steps=steps, since=since, columns=columns, merges=len(merged), reverted=reverted, text=text
    )


async def weekly_throughput(deps: Deps, repository: str | None) -> list[int]:
    """Tickets first reaching review in each of the last eight UTC weeks, oldest first."""
    repos = await deps.repositories(repository)
    return throughput([timeline_of(t) for _, t in await timelines_of(deps, repos)], deps.seconds())


async def forecast_open(deps: Deps, open_tickets: int | None, repository: str | None) -> Forecast:
    """When the open tickets are done, drawn from the daily counts of the last 56 days."""
    if open_tickets is not None and open_tickets < 0:
        msg = "open must be at least 0: it is how many tickets are left to finish"
        raise BadRequestError(msg)
    repos = await deps.repositories(repository)
    tickets = [t for _, t in await timelines_of(deps, repos)]
    sample = daily_counts([timeline_of(t) for t in tickets], deps.seconds())
    if open_tickets is None:
        before_review = stage_index("review")
        open_tickets = sum(
            1 for t in tickets if not t.archived and stage_index(t.stage) < before_review
        )
    days = forecast(sample, open_tickets)
    return Forecast(
        p50=None if days is None else days[0],
        p85=None if days is None else days[1],
        open=open_tickets,
        sample=sample,
    )


def _unfinished(exit_code: int | None, commits: list[str] | None) -> bool:
    """Ended and not cleanly: a failure or stop, or a clean exit that committed nothing."""
    return exit_code is not None and (exit_code != 0 or commits == [])


async def factory_yields(deps: Deps, repository: str | None) -> list[Yield]:
    """How each agent and model's merged work held up, over the last 90 days of runs."""
    repos = await deps.repositories(repository)
    now = deps.seconds()
    names = [r.name for r in repos]
    async with deps.uow() as session:
        merged = await MetricsRepository(session).merges_since(now - YIELD_LOOKBACK_S, names)
    facts = {(repo, t.id): t for repo, t in await timelines_of(deps, repos)}
    causes: dict[tuple[str, str], list[str]] = {}
    for (repo, _), found in facts.items():
        for cause in found.caused_by:
            causes.setdefault((repo, cause), []).append(found.id)
    rows = [
        FactoryRow(
            repository=m.repository,
            ticket=m.ticket,
            intake_to_merge=m.at - facts[(m.repository, m.ticket)].created_at.timestamp(),
            escaped=tuple(sorted(set(causes.get((m.repository, m.ticket), [])))),
        )
        for m in merged
        if m.ticket is not None and (m.repository, m.ticket) in facts
    ]
    runs = await deps.ports.runs.since(instant(now - YIELD_LOOKBACK_S))
    worked = [
        BoardRun(
            repository=r.repository,
            ticket=r.ticket_id,
            agent=r.agent,
            model=r.model,
            stage=r.stage,
            cost=r.cost,
            unfinished=_unfinished(r.exit_code, r.commits),
        )
        for r in runs
        if r.repository in names
    ]
    return yields(rows, worked)


def reached_done(moves: Sequence[StageMove]) -> datetime | None:
    """When a ticket with these moves (oldest first) first reached review or later, else None."""
    done = stage_index("review")
    return next((m.at for m in moves if stage_index(m.to) >= done), None)
