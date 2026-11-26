"""Fake ports for the hooks service: each answers what a test sets and keeps what it was asked."""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from code_factory.hooks.models import ReleaseFact, TellConfirm
from code_factory.hooks.ports import (
    BoardAddress,
    Checkout,
    HookPorts,
    MemoryContext,
    MemoryRecall,
    NewBug,
    NewsFact,
    TicketFacts,
)
from code_factory.hooks.service import HookService
from code_factory.platform.errors import ConflictError, NotFoundError
from code_factory.platform.identity import Actor, Role
from code_factory.tickets.models import Activity

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
STARTED = NOW - timedelta(minutes=5)
TICKET = TicketFacts(
    id="CF-5",
    repository="sample",
    title="Work",
    stage="build",
    branch="ticket/cf-5",
    labels=["ui"],
)


def run_actor(**fields: object) -> Actor:
    """The actor of a build run on CF-5."""
    base: dict[str, object] = {
        "role": Role.RUN,
        "subject": "run:r-1",
        "token_id": 1,
        "run_id": "r-1",
        "ticket_id": "CF-5",
        "stage": "build",
        "repository": "sample",
        "expires_at": NOW + timedelta(hours=1),
    }
    return Actor(**(base | fields))  # ty: ignore[invalid-argument-type]


OWNER_ACTOR = run_actor(
    role=Role.OWNER, subject="owner:me", run_id=None, ticket_id=None, stage=None, repository=None
)


@dataclass
class FakeTalk:
    news: NewsFact | None = None
    peeked: list[tuple[str, str, datetime]] = field(default_factory=list)
    confirmed: list[tuple[str, str, TellConfirm]] = field(default_factory=list)

    async def peek(self, ticket_id: str, session_id: str, since: datetime) -> NewsFact | None:
        self.peeked.append((ticket_id, session_id, since))
        return self.news

    async def confirm(self, ticket_id: str, session_id: str, marks: TellConfirm) -> None:
        self.confirmed.append((ticket_id, session_id, marks))


ALLOW = {
    "hookSpecificOutput": {
        "hookEventName": "PermissionRequest",
        "decision": {"behavior": "allow"},
    }
}


@dataclass
class FakePermissions:
    """Answers `answer`, or holds the request until `release` is set or it is cancelled."""

    answer: dict[str, Any] = field(default_factory=lambda: ALLOW)
    hold: bool = False
    requests: list[tuple[str, dict[str, Any], bool, float]] = field(default_factory=list)
    recorded: list[tuple[str, str, bool, str, str]] = field(default_factory=list)
    standing: list[str] = field(default_factory=list)
    cancelled: int = 0
    finished: int = 0
    error: Exception | None = None
    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def request(
        self, run_id: str, payload: dict[str, Any], *, sandboxed: bool, wait: float
    ) -> dict[str, Any]:
        self.requests.append((run_id, payload, sandboxed, wait))
        if self.error is not None:
            raise self.error
        if self.hold:
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled += 1
                raise
            finally:
                self.finished += 1
        return self.answer

    async def record(
        self,
        run_id: str,
        tool: str,
        *,
        allow: bool,
        by: Literal["policy", "reviewer", "owner"],
        reason: str,
    ) -> None:
        self.recorded.append((run_id, tool, allow, by, reason))

    async def rules(self) -> list[str]:
        return self.standing

    def kind(self, tool: str, tool_input: object) -> str | None:
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        return f"Bash({command} *)" if tool == "Bash" and command else (tool or None)


@dataclass
class FakeRuns:
    at: datetime | None = STARTED

    async def started(self, run_id: str) -> datetime | None:  # noqa: ARG002
        return self.at


@dataclass
class FakeTickets:
    tickets: dict[str, TicketFacts] = field(default_factory=lambda: {"CF-5": TICKET})
    branches: dict[tuple[str, str], TicketFacts] = field(default_factory=dict)
    rows: list[str] = field(default_factory=list)
    recorded: list[tuple[str, str, dict[str, object], str]] = field(default_factory=list)
    fail_record: bool = False
    sources: dict[tuple[str, str], TicketFacts] = field(default_factory=dict)
    report_counts: dict[str, int] = field(default_factory=dict)
    bugs: list[NewBug] = field(default_factory=list)
    records: list[tuple[str, Activity]] = field(default_factory=list)
    raced_by: TicketFacts | None = None  # another report files the source first

    async def get(self, ticket_id: str) -> TicketFacts:
        if ticket_id not in self.tickets:
            msg = f"no ticket {ticket_id}"
            raise NotFoundError(msg)
        return self.tickets[ticket_id]

    async def by_branch(self, repository: str, branch: str) -> TicketFacts | None:
        return self.branches.get((repository, branch))

    async def requirements(self, ticket_id: str) -> list[str]:  # noqa: ARG002
        return self.rows

    async def record(self, ticket_id: str, kind: str, data: dict[str, object], by: str) -> None:
        if self.fail_record:
            msg = "the database is gone"
            raise ConnectionError(msg)
        self.recorded.append((ticket_id, kind, data, by))

    async def by_source(self, repository: str, source: str) -> TicketFacts | None:
        return self.sources.get((repository, source))

    async def reports(self, ticket_id: str) -> int:
        return self.report_counts.get(ticket_id, 0)

    async def create_bug(self, bug: NewBug) -> str:
        if self.raced_by is not None:
            self.sources[(bug.repository, bug.source)] = self.raced_by
            raise ConflictError(f"{bug.source} is filed already")
        self.bugs.append(bug)
        found = TicketFacts(
            id=f"CF-{100 + len(self.bugs)}",
            repository=bug.repository,
            title=bug.title,
            stage="spec",
        )
        self.sources[(bug.repository, bug.source)] = found
        return found.id

    async def activity(self) -> list[tuple[str, Activity]]:
        return self.records


@dataclass
class FakeMemory:
    recall_given: MemoryRecall = field(default_factory=MemoryRecall)
    asked: list[tuple[str, MemoryContext, str | None, str | None]] = field(default_factory=list)

    async def recall(
        self, repository: str, context: MemoryContext, *, ticket_id: str | None, run_id: str | None
    ) -> MemoryRecall:
        self.asked.append((repository, context, ticket_id, run_id))
        return self.recall_given


@dataclass
class FakeCheckouts:
    found: Checkout | None = None
    paths: list[str] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)

    async def of(self, cwd: str) -> Checkout | None:
        self.asked.append(cwd)
        return self.found

    async def changed(self, repository: str, branch: str) -> list[str]:  # noqa: ARG002
        return self.paths


@dataclass
class FakeAuth:
    minted: list[str] = field(default_factory=list)
    spent: list[str] = field(default_factory=list)
    ended: int = 0

    async def mint(self) -> str:
        self.minted.append(f"nonce{len(self.minted) + 1}")
        return self.minted[-1]

    async def spend(self, nonce: str) -> None:
        self.spent.append(nonce)

    async def end_sessions(self) -> int:
        return self.ended


@dataclass
class FakeReleases:
    releases: list[ReleaseFact] = field(default_factory=list)
    days: int | None = None

    async def published(self, repository: str) -> list[ReleaseFact]:  # noqa: ARG002
        return self.releases

    async def watch_days(self, repository: str) -> int | None:  # noqa: ARG002
        return self.days


@dataclass
class FakeRepositories:
    names: set[str] = field(default_factory=lambda: {"sample"})

    async def exists(self, name: str) -> bool:
        return name in self.names


@dataclass
class FakeOpener:
    opened: list[str] = field(default_factory=list)
    error: Exception | None = None

    async def open_url(self, url: str) -> None:
        if self.error is not None:
            raise self.error
        self.opened.append(url)


@dataclass
class FakeProbe:
    answers: bool = True
    asked: list[str] = field(default_factory=list)

    async def up(self, base: str) -> bool:
        self.asked.append(base)
        return self.answers


@dataclass
class Fakes:
    """Every fake, and the service built over them."""

    talk: FakeTalk = field(default_factory=FakeTalk)
    permissions: FakePermissions = field(default_factory=FakePermissions)
    runs: FakeRuns = field(default_factory=FakeRuns)
    tickets: FakeTickets = field(default_factory=FakeTickets)
    memory: FakeMemory = field(default_factory=FakeMemory)
    checkouts: FakeCheckouts = field(default_factory=FakeCheckouts)
    auth: FakeAuth = field(default_factory=FakeAuth)
    releases: FakeReleases = field(default_factory=FakeReleases)
    repositories: FakeRepositories = field(default_factory=FakeRepositories)
    opener: FakeOpener = field(default_factory=FakeOpener)
    probe: FakeProbe = field(default_factory=FakeProbe)

    def service(self, **options: Any) -> HookService:  # noqa: ANN401  # the service's own options
        ports = HookPorts(
            talk=self.talk,
            permissions=self.permissions,
            runs=self.runs,
            tickets=self.tickets,
            memory=self.memory,
            checkouts=self.checkouts,
            auth=self.auth,
            releases=self.releases,
            repositories=self.repositories,
            opener=self.opener,
            probe=self.probe,
            board=BoardAddress(host="127.0.0.1", port=8080),
        )
        return HookService(ports, clock=lambda: NOW, **options)
