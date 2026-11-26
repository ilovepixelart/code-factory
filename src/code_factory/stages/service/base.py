"""What the stage service is made of.

The services it reads, the settings it reads from them and the ledger records the fix loop reads.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import NotFoundError
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.settings.models import reviews
from code_factory.settings.service import SettingsService
from code_factory.stages.adapters import GitRunner, config_has_content
from code_factory.stages.models import BranchFacts, Record
from code_factory.stages.ports import FactsSource
from code_factory.stages.tables import StageFactsRow
from code_factory.tickets.models import PullRequestState, Ticket, TicketFilter
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)

DEFAULT_ROUNDS = 3
DEFAULT_RUN_TIMEOUT = 3600
ACTOR = "board"


def utc_now() -> datetime:
    """The service's default clock."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class Ports:
    """The other modules' services the stage service reads."""

    tickets: TicketService
    reviews: ReviewService
    activity: ActivityService
    documents: DocumentService
    releases: ReleaseService
    repositories: RepositoryService
    settings: SettingsService
    facts: FactsSource


@dataclass(frozen=True)
class Agents:
    """The `[agents]` and `[merge]` settings the stage decisions read, with their defaults."""

    fix_rounds: int = DEFAULT_ROUNDS
    review_rounds: int = DEFAULT_ROUNDS
    review: bool = False
    run_timeout: int = DEFAULT_RUN_TIMEOUT
    large_change: int | None = None
    sensitive_paths: tuple[str, ...] = ()
    unreviewed_lines: int | None = None
    sensitive: tuple[str, ...] = ()
    unreadable: bool = False


class StageBase:
    """The shared state of the stage service's parts: the unit of work, ports and clock."""

    def __init__(
        self,
        uow: UnitOfWork,
        ports: Ports,
        *,
        clock: Callable[[], datetime] = utc_now,
        git: GitRunner | None = None,
    ) -> None:
        self._uow = uow
        self._ports = ports
        self._clock = clock
        self._git = git or GitRunner()
        self._facts = ports.facts

    async def _number(self, ticket: str) -> int:
        """The number of the ticket `CF-<n>`; `NotFoundError` when there is none."""
        return (await self._ports.tickets.get(ticket)).number

    async def _numbers(self, ids: Sequence[str] | None) -> dict[int, str]:
        """Each live ticket's number and id, for these ids (every one without `ids`)."""
        live = await self._ports.tickets.list(TicketFilter(archived=None))
        wanted = None if ids is None else set(ids)
        return {t.number: t.id for t in live if wanted is None or t.id in wanted}

    async def _root(self, repository: str) -> Path:
        return await self._ports.repositories.get(repository)

    async def _agents(self, repository: str) -> Agents:
        """The repository's settings; the defaults when it is not tracked or has no config."""
        try:
            root = await self._root(repository)
        except NotFoundError:
            return Agents()
        config = await self._ports.settings.load(root)
        agents, merge = config.agents, config.merge
        rounds = _rounds(agents.fix_rounds if agents is not None else None)
        return Agents(
            fix_rounds=rounds,
            review_rounds=_rounds(agents.review_rounds if agents is not None else None),
            review=agents is not None and reviews(agents),
            run_timeout=(
                agents.run_timeout
                if agents is not None and agents.run_timeout is not None
                else DEFAULT_RUN_TIMEOUT
            ),
            large_change=agents.large_change if agents is not None else None,
            sensitive_paths=tuple(agents.sensitive_paths or ()) if agents is not None else (),
            unreviewed_lines=merge.unreviewed_lines if merge is not None else None,
            sensitive=tuple(merge.sensitive or ()) if merge is not None else (),
            unreadable=not config.model_dump(exclude_none=True) and await config_has_content(root),
        )

    async def _records(self, ticket_id: str) -> list[Record]:
        """The ticket's ledger as the fix loop reads it; the one place that knows its shape."""
        entries = await self._ports.activity.entries(ticket_id)
        return [Record(kind=e.kind, at=e.at, data=e.data) for e in entries]


def _rounds(configured: int | None) -> int:
    return DEFAULT_ROUNDS if configured is None else configured


def opened_address(ticket: Ticket) -> str | None:
    """The address of the ticket's recorded pull request; `None` without one that is not closed."""
    pull = ticket.pull_request
    if pull is None or pull.state is PullRequestState.CLOSED:
        return None
    return pull.url


def ticket_facts(ticket: Ticket, row: StageFactsRow | None) -> tuple[BranchFacts, bool]:
    """The branch facts to judge the ticket by, and whether they are the observer's own.

    Without a row read for the ticket's current branch, a declared branch counts as started and a
    recorded pull request as pushed until the observer reads git. A merge the ticket records
    counts whatever git says.
    """
    pull = ticket.pull_request
    recorded_merge = ticket.merged or (pull is not None and pull.state is PullRequestState.MERGED)
    if row is None or row.branch != ticket.branch:
        fallback = BranchFacts(
            known=False,
            local=bool(ticket.branch),
            pushed=pull is not None,
            merged=recorded_merge,
        )
        return fallback, False
    stored = BranchFacts(
        known=row.known,
        local=row.local,
        pushed=row.pushed,
        in_worktree=row.in_worktree,
        merged=row.merged or recorded_merge,
        has_commits=row.has_commits,
        untraced=row.untraced,
        default_branch=row.default_branch,
        head=row.head,
    )
    return stored, True
