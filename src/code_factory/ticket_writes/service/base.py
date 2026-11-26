"""What every part of the ticket write service shares: its ports, clock, units and undo offers."""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from code_factory.git.models import GitFacts
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.repositories.service import RepositoryService
from code_factory.stages.service import StageService
from code_factory.ticket_writes.models import UpdatePlan
from code_factory.ticket_writes.rules import branch_missing, known_repository, written_fields
from code_factory.tickets.models import TicketAddress, TicketCore, TicketFields
from code_factory.tickets.service import TicketService, TicketUnit, utc_now
from code_factory.undo.models import Changed
from code_factory.undo.service import UndoService

KIND = "tickets.revert"
NO_TICKET = "no such ticket"
ActiveRuns = Callable[[TicketAddress], Awaitable[bool]]
DuplicateQuestion = Callable[[str, str], Awaitable[str]]


class GitPort(Protocol):
    """What the writes read of git: the branches of a repository and what a name may be."""

    async def facts(self, repository: str) -> GitFacts:
        """The repository's branches."""
        ...

    @staticmethod
    def branch_refusal(name: str) -> str | None:
        """Why `name` is not a plain branch name, `None` when it is."""
        ...


@dataclass(frozen=True)
class WritePorts:
    """The other modules' services the write service calls."""

    tickets: TicketService
    stages: StageService
    git: GitPort
    repositories: RepositoryService


async def write_plan(unit: TicketUnit, ref: TicketAddress, plan: UpdatePlan, *, by: str) -> None:
    """Write what an update plan names, then its records, in the unit."""
    fields = {name: value for name, value in plan.values.items() if name != "branch"}
    if fields:
        await unit.save_fields(ref, TicketFields.model_validate(written_fields(fields)))
    if "branch" in plan.values:
        await unit.set_branch(ref, plan.values["branch"])
    if plan.archived is not None:
        await unit.set_archived(ref, archived=plan.archived)
    for record in plan.activity:
        await unit.record(ref, record.kind, record.data, by=by)


def undo_fields(ref: TicketAddress, to: dict[str, str], expect: dict[str, str]) -> dict[str, Any]:
    """The stored inverse of a field change: put `to` back while the fields still hold `expect`."""
    return {"op": "fields", "repository": ref.repository, "id": ref.id, "to": to, "expect": expect}


class WriteBase:
    """The shared state of the write service's parts."""

    def __init__(
        self,
        uow: UnitOfWork,
        ports: WritePorts,
        undo: UndoService,
        *,
        clock: Callable[[], datetime] = utc_now,
        write_wait: float = 20.0,
    ) -> None:
        self._uow = uow
        self._ports = ports
        self._undo = undo
        self._clock = clock
        self._write_wait = write_wait
        self._active_runs: ActiveRuns | None = None
        self._duplicate_question: DuplicateQuestion | None = None

    def bind_active_runs(self, check: ActiveRuns) -> None:
        """Say how to tell that an agent is running on a ticket; unbound means none is."""
        self._active_runs = check

    def bind_duplicate_question(self, ask: DuplicateQuestion) -> None:
        """Say how to ask about open tickets that look like a new one; unbound asks nothing."""
        self._duplicate_question = ask

    def _unit(self, repositories: list[str]) -> AbstractAsyncContextManager[TicketUnit]:
        return self._ports.tickets.unit(repositories, wait=self._write_wait)

    async def _core(self, ref: TicketAddress) -> TicketCore:
        """The live ticket; `NotFoundError` for one that is not there or an id that names none."""
        try:
            found = await self._ports.tickets.get_core(ref)
        except BadRequestError:
            found = None
        if found is None:
            raise NotFoundError(NO_TICKET)
        return found

    async def _known_repository(self, repository: str) -> None:
        tracked = {record.name for record in await self._ports.repositories.list()}
        filed = set(await self._ports.tickets.list_repositories())
        if not known_repository(repository, tracked=tracked, filed=filed):
            msg = "unknown repository"
            raise BadRequestError(msg)

    async def _branch_gone(self, repository: str, branch: str, held: str) -> None:
        """Refuse a branch no ref holds; the held name, none and unreadable git pass."""
        if not branch or branch == held or self._ports.git.branch_refusal(branch) is not None:
            return
        facts = await self._ports.git.facts(repository)
        if not facts.known:
            return
        refusal = branch_missing(branch, facts.local, facts.remote, facts.default_branch)
        if refusal is not None:
            raise BadRequestError(refusal)

    async def _offer(self, ops: list[dict[str, Any]], notice: str) -> Changed:
        return await self._undo.offer(KIND, {"ops": ops}, notice)
