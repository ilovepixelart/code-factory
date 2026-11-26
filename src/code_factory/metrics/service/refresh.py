"""One pass over a repository: the merge ledger and the branch cuts, written from git."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from code_factory.metrics.models import (
    Autonomy,
    ChecksVerdict,
    Merge,
    MergeFact,
    RefreshResult,
    RunFacts,
    TrackedRepo,
)
from code_factory.metrics.repository import MetricsRepository
from code_factory.metrics.rules.merges import autonomy_class, checks_verdict, parse_merges
from code_factory.metrics.rules.reverts import reverted_commits
from code_factory.metrics.service.deps import DAY, Deps, instant

WINDOW_S = 30 * DAY  # merges of the last 30 days are kept current
LOG_BEFORE_S = 30 * DAY  # read this much earlier, so a branch's first commit is found
SETTLED_AFTER_S = DAY  # a row older than this keeps the class and verdict it has
IN_FLIGHT = ["build", "review"]


def _unsettled(known: MergeFact, now: float) -> bool:
    young = now - known.at < SETTLED_AFTER_S
    return young and (known.autonomy == Autonomy.UNKNOWN or known.checks == ChecksVerdict.NONE)


async def _classify(
    deps: Deps, repo: TrackedRepo, merge: Merge, runs: Sequence[RunFacts]
) -> Autonomy:
    own = [r for r in runs if r.repository == repo.name and r.ticket_id == merge.ticket]
    recorded = [r.commits for r in own if r.commits is not None]
    if not recorded:
        return Autonomy.UNKNOWN
    made = {sha for commits in recorded for sha in commits}
    rev_list = await deps.git.autonomy_range(repo.path, merge.commit)
    return autonomy_class(rev_list, made, recorded=True)


@dataclass(frozen=True)
class _Log:
    """What one pass read from git, and the rows the ledger held before it."""

    merges: Sequence[Merge]
    reverted: set[str]
    known: dict[str, MergeFact]
    now: float


async def _rows(deps: Deps, repo: TrackedRepo, seen: _Log) -> list[MergeFact]:
    """The ledger rows of the merges: a new or still unsettled row is classed, the rest kept."""
    merges, reverted, known, now = seen.merges, seen.reverted, seen.known, seen.now
    needy = [m for m in merges if m.commit not in known or _unsettled(known[m.commit], now)]
    runs = await deps.ports.runs.since(instant(now - WINDOW_S - LOG_BEFORE_S)) if needy else []
    tickets = sorted({m.ticket for m in needy if m.ticket is not None})
    records = await deps.ports.checks.records(repo.name, tickets) if tickets else []
    needed = {m.commit for m in needy}
    rows: list[MergeFact] = []
    for merge in merges:
        if merge.commit in needed:
            autonomy = await _classify(deps, repo, merge, runs)
            checks = checks_verdict(records, merge.head)
        else:
            autonomy, checks = known[merge.commit].autonomy, known[merge.commit].checks
        rows.append(
            MergeFact(
                **merge.model_dump(),
                repository=repo.name,
                reverted=merge.commit in reverted,
                autonomy=autonomy,
                checks=checks,
            )
        )
    return rows


async def _new_cuts(
    deps: Deps, repo: TrackedRepo, recorded: dict[str, float | None]
) -> tuple[dict[str, float | None], list[str]]:
    """The cuts to write and every branch in flight: new ones, and those git could not place."""
    flight = await deps.ports.tickets.flow_facts(repo.name, stages=IN_FLIGHT)
    branches = sorted({t.branch for t in flight if t.branch and not t.archived})
    todo = [b for b in branches if recorded.get(b) is None]
    base = await deps.ports.repositories.default_branch(repo.name) if todo else ""
    found = {b: await deps.git.branch_cut(repo.path, base, b) for b in todo}
    return found, branches


async def refresh_repository(deps: Deps, repo: TrackedRepo) -> RefreshResult:
    """Bring the ledger and the branch cuts of `repo` up to date from its default branch's log.

    `reverted` is rewritten for every row of the window, rows of the window absent from the log
    are deleted (the history was rewritten), and a row older than a day keeps its class and verdict.
    Raises `GitUnavailableError` when git cannot read the log.
    """
    async with deps.git.exclusive(repo.path):
        now = deps.seconds()
        window_start = now - WINDOW_S
        base = await deps.ports.repositories.default_branch(repo.name)
        log = await deps.git.log(repo.path, base, window_start - LOG_BEFORE_S)
        merges = await asyncio.to_thread(parse_merges, log, window_start)
        reverted = await asyncio.to_thread(reverted_commits, log)
        async with deps.uow() as session:
            store = MetricsRepository(session)
            known = {m.commit: m for m in await store.merges_since(window_start, [repo.name])}
            recorded = await store.cuts(repo.name)
        rows = await _rows(deps, repo, _Log(merges, reverted, known, now))
        new_cuts, branches = await _new_cuts(deps, repo, recorded)
        async with deps.uow() as session:
            store = MetricsRepository(session)
            await store.upsert_merges(rows, now)
            await store.delete_merges(
                repo.name, [c for c in known if c not in {m.commit for m in merges}]
            )
            await store.upsert_cuts(repo.name, new_cuts, now)
            await store.delete_cuts_except(repo.name, branches)
    return RefreshResult(
        repository=repo.name,
        seen=len(rows),
        inserted=sum(row.commit not in known for row in rows),
        reverted=sum(row.reverted for row in rows),
        cuts=len(new_cuts),
    )
