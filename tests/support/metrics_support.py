"""Fakes for the module's four ports, dated git history and a service built over them."""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from code_factory.metrics.adapters import GitReader
from code_factory.metrics.models import (
    CheckRecord,
    RunFacts,
    StageMove,
    StepRun,
    TicketFlow,
    TrackedRepo,
)
from code_factory.metrics.ports import MetricsPorts
from code_factory.metrics.service import MetricsService
from code_factory.platform.db import UnitOfWork
from git_support import ENV, commit, git, make_repo

NOW = 1_790_001_000.0  # 2026-09-21T14:30:00Z
DAY = 86400.0
HOUR = 3600.0


def when(seconds: float) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)


@dataclass
class FakeRepositories:
    repos: list[TrackedRepo] = field(default_factory=list)
    bases: dict[str, str] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)
    begun: asyncio.Event = field(default_factory=asyncio.Event)

    async def tracked(self) -> list[TrackedRepo]:
        return list(self.repos)

    async def default_branch(self, name: str) -> str:
        self.asked.append(name)
        self.begun.set()
        return self.bases.get(name, "main")


@dataclass
class FakeTickets:
    facts: dict[str, list[TicketFlow]] = field(default_factory=dict)
    calls: list[tuple[str, Sequence[str] | None, Sequence[str] | None]] = field(
        default_factory=list
    )
    cause_calls: list[tuple[str, Sequence[str]]] = field(default_factory=list)

    async def flow_facts(
        self,
        repository: str,
        ids: Sequence[str] | None = None,
        stages: Sequence[str] | None = None,
        causes: Sequence[str] | None = None,
    ) -> list[TicketFlow]:
        if causes is None:
            self.calls.append((repository, ids, stages))
        else:
            self.cause_calls.append((repository, causes))
        return [
            t
            for t in self.facts.get(repository, [])
            if (ids is None or t.id in ids)
            and (stages is None or t.stage in stages)
            and (causes is None or set(causes) & set(t.caused_by))
        ]


@dataclass
class FakeRuns:
    runs: list[RunFacts] = field(default_factory=list)
    starts: dict[str, dict[str, datetime]] = field(default_factory=dict)
    asked_since: list[datetime] = field(default_factory=list)

    async def since(self, since: datetime) -> list[RunFacts]:
        self.asked_since.append(since)
        return [r for r in self.runs if r.started_at >= since]

    async def build_starts(
        self, repository: str, since: datetime, until: datetime
    ) -> dict[str, datetime]:
        return {
            ticket: at
            for ticket, at in self.starts.get(repository, {}).items()
            if since <= at <= until
        }


@dataclass
class FakeChecks:
    records_: list[CheckRecord] = field(default_factory=list)
    steps: list[StepRun] = field(default_factory=list)
    asked: list[tuple[str, Sequence[str]]] = field(default_factory=list)

    async def records(self, repository: str, tickets: Sequence[str]) -> list[CheckRecord]:
        self.asked.append((repository, tickets))
        return [r for r in self.records_ if r.ticket_id in tickets]

    async def step_runs(self, newest: int | None) -> list[StepRun]:
        ordered = sorted(self.steps, key=lambda s: s.at, reverse=True)
        return ordered if newest is None else ordered[:newest]


@dataclass
class World:
    """The four fakes of one test, and the clock the service reads."""

    repositories: FakeRepositories = field(default_factory=FakeRepositories)
    tickets: FakeTickets = field(default_factory=FakeTickets)
    runs: FakeRuns = field(default_factory=FakeRuns)
    checks: FakeChecks = field(default_factory=FakeChecks)
    now: float = NOW

    def ports(self) -> MetricsPorts:
        return MetricsPorts(self.repositories, self.tickets, self.runs, self.checks)

    def service(
        self, uow: UnitOfWork, reader: GitReader | None = None, **options: float
    ) -> MetricsService:
        clock: Callable[[], datetime] = lambda: when(self.now)  # noqa: E731
        return MetricsService(uow, self.ports(), reader or GitReader(), clock, **options)

    def track(self, root: Path, base: str = "main") -> None:
        self.repositories.repos.append(TrackedRepo(name=root.name, path=root))
        self.repositories.bases[root.name] = base


def ticket(  # noqa: PLR0913  # a fixture builder, all but the first two optional
    ticket_id: str,
    created_at: float,
    *,
    stage: str = "merged",
    branch: str = "",
    caused_by: Sequence[str] = (),
    moves: Sequence[tuple[float, str]] = (),
    archived: bool = False,
    needs: str = "",
    title: str = "",
) -> TicketFlow:
    return TicketFlow(
        id=ticket_id,
        title=title or f"Idea {ticket_id}",
        stage=stage,
        archived=archived,
        branch=branch,
        created_at=when(created_at),
        caused_by=list(caused_by),
        needs=needs,
        moves=[StageMove(at=when(at), to=to) for at, to in moves],
    )


def run_facts(  # noqa: PLR0913  # a fixture builder, all but the first two optional
    ticket_id: str,
    started: float,
    *,
    repository: str = "sample",
    stage: str = "build",
    model: str = "opus",
    agent: str = "",
    cost: float | None = None,
    commits: Sequence[str] | None = None,
    exit_code: int | None = 0,
) -> RunFacts:
    return RunFacts(
        repository=repository,
        ticket_id=ticket_id,
        stage=stage,
        agent=agent,
        model=model,
        connection="",
        started_at=when(started),
        exit_code=exit_code,
        halted="",
        tokens=None,
        cost=cost,
        cost_estimated=False,
        commits=None if commits is None else list(commits),
    )


def at_time(seconds: float) -> dict[str, str]:
    return {
        "GIT_AUTHOR_DATE": f"{int(seconds)} +0000",
        "GIT_COMMITTER_DATE": f"{int(seconds)} +0000",
    }


def commit_at(root: Path, seconds: float, subject: str, **files: str) -> str:
    """A commit whose author and committer dates are `seconds`; returns its hash."""
    with patch.dict(ENV, at_time(seconds)):
        return commit(root, subject, **files)


def pull_request(root: Path, number: int, branch: str, seconds: float, message: str = "") -> str:
    """Commit one file on `branch` at `seconds` and merge it into main as pull request `number`.

    Returns the hash of the merge commit; the merge is dated one minute later.
    """
    git(root, "checkout", "-q", "-b", branch)
    commit_at(root, seconds, message or f"{branch}: work", **{f"src{number}.txt": "work\n"})
    git(root, "checkout", "-q", "main")
    with patch.dict(ENV, at_time(seconds + 60)):
        git(
            root,
            "merge",
            "-q",
            "--no-ff",
            "-m",
            f"Merge pull request #{number} from o/{branch}",
            branch,
        )
    return git(root, "rev-parse", "HEAD")


def sample_repo(base: Path) -> Path:
    """A repository `sample` whose first commit is dated before every test event."""
    with patch.dict(ENV, at_time(NOW - 20 * DAY)):
        return make_repo(base, "sample")
