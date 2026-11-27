"""What every part of the check service shares: the services it reads, the adapters, the clock."""

import asyncio
import logging
import os
import socket
import uuid
from collections import deque
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import anyio

from code_factory.agents.service import AgentService
from code_factory.checks.adapters import (
    CheckoutDenials,
    CheckPolicy,
    ContainerChecks,
    HeavyLockFile,
    LogFiles,
    TreeJudge,
    Workspaces,
    sleep_time,
)
from code_factory.checks.models import CheckRun, ChecksView
from code_factory.checks.ports import ForgePort
from code_factory.checks.repository import CheckStore
from code_factory.checks.rules import LOCK_FILE
from code_factory.checks.rules.spec import receipt_files
from code_factory.checks.service.permit import Permit
from code_factory.git.service import GitService
from code_factory.platform.contained import ContainedRunner, SandboxSettings
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, NotFoundError, UnavailableError
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.settings.service import SettingsService
from code_factory.stages.service import StageService
from code_factory.tickets.service import ActivityService, TicketService

logger = logging.getLogger(__name__)
ACTOR = "board"
CLEANUP_S = 10.0
SPEC_RECEIPT_BYTES = 64 * 1024
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """The service's default clock."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class CheckDeps:
    """The services and ports the check service reads."""

    tickets: TicketService
    activity: ActivityService
    stages: StageService
    git: GitService
    settings: SettingsService
    repositories: RepositoryService
    releases: ReleaseService
    agents: AgentService
    forge: ForgePort
    sandbox: SandboxSettings
    denials: CheckoutDenials
    verify_claim: Callable[[str], AbstractAsyncContextManager[bool]]


@dataclass(frozen=True)
class CheckOptions:
    """How a check service runs: where its files are and how long it waits."""

    state_dir: Path
    concurrency: int = 4
    heartbeat_s: float = 10.0
    turn_poll_s: float = 0.2
    shutdown_s: float = 10.0
    program: str = "srt"
    sleep_time: Callable[[], Awaitable[str | None]] = field(default=sleep_time)


def process_token() -> str:
    """`<host>:<pid>:<uuid4>`: what a row says of the process that runs it."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4()}"


class CheckBase:
    """The state of a `CheckService`: unit of work, services, adapters and what runs here."""

    def __init__(
        self, uow: UnitOfWork, deps: CheckDeps, options: CheckOptions, clock: Clock = utc_now
    ) -> None:
        self._uow = uow
        self._deps = deps
        self._opts = options
        self._clock = clock
        self._owner = process_token()
        state = options.state_dir
        self._spec_state = state.resolve()
        self._logs = LogFiles(state)
        self._policy = CheckPolicy(deps.settings, deps.repositories, deps.git, state)
        self._runner = ContainedRunner(
            policy=self._policy, sandbox=deps.sandbox, state_dir=state, program=options.program
        )
        self._workspaces = Workspaces(deps.git, self._runner, state)
        self._judge_tree = TreeJudge(self._policy.places)
        self._containers = ContainerChecks(
            agents=deps.agents,
            git=deps.git,
            logs=self._logs,
            places=self._policy.places,
            state_dir=state,
            denials=deps.denials,
        )
        locks = state.with_name(f"{state.name}-locks")
        self._heavy = HeavyLockFile(locks / LOCK_FILE)
        self._admission_limit = max(options.concurrency, 1)
        self._slots = asyncio.Semaphore(self._admission_limit)
        self._wake = asyncio.Event()
        self._admitted: set[int] = set()
        self._release_candidates: deque[str] = deque()
        self._release_tasks: dict[str, asyncio.Task[None]] = {}
        self._spec_tasks: dict[str, asyncio.Task[None]] = {}
        self._spec_failures: dict[str, tuple[str, str, str, float]] = {}
        self._draining = False
        self._group: asyncio.TaskGroup | None = None
        self._running: dict[int, asyncio.Task[object]] = {}
        self._permits: dict[int, Permit] = {}
        self._trees: dict[int, str] = {}
        self._verifying: set[str] = set()

    def _now(self) -> datetime:
        return self._clock()

    @asynccontextmanager
    async def _db(self) -> AsyncGenerator[CheckStore]:
        """One short transaction over the checks tables; no subprocess runs inside it."""
        async with self._uow() as session:
            yield CheckStore(session)

    async def _root(self, repository: str) -> Path:
        return await self._deps.repositories.get(repository)

    async def _spec_refusal(self, repository: str, ticket: str, head: str) -> str | None:
        """Read only the owner's receipt, then compare its locked files by Git object."""
        git = self._deps.git
        try:
            text = await git.read_text_below(
                self._spec_state, f"spec-locks/{ticket}.json", SPEC_RECEIPT_BYTES
            )
        except BadRequestError:
            return f"Spec lock could not read the owner receipt for {ticket}."
        if text is None:
            return None
        return await self._sealed_files_refusal(repository, ticket, head, text)

    async def _sealed_files_refusal(
        self, repository: str, ticket: str, head: str, text: str
    ) -> str | None:
        try:
            sealed, paths = receipt_files(text)
        except TypeError, ValueError:
            return f"Spec lock could not read the owner receipt for {ticket}."
        try:
            changed = await self._deps.git.changed_files(repository, sealed, head, paths)
        except UnavailableError as error:
            return f"Spec lock could not compare the sealed files. {error}."
        if changed:
            named = ", ".join(repr(path) for path in changed)
            return f"Spec lock refused {named}. Restore the sealed files."
        return None

    async def _row(self, check_id: int) -> CheckRun:
        async with self._db() as store:
            row = await store.runs.get(check_id)
        if row is None:
            msg = "no such check"
            raise NotFoundError(msg)
        return row

    async def _cleanup[T](self, work: Awaitable[T]) -> T | None:
        """Finish `work` even while the caller is being cancelled, for at most 10 s."""
        with anyio.CancelScope(shield=True), anyio.move_on_after(CLEANUP_S):
            return await work
        return None


__all__ = ["ACTOR", "CheckBase", "CheckDeps", "CheckOptions", "ChecksView", "utc_now"]
