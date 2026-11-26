"""Fakes for the ticket write tests: git's branches and the bound questions about runs."""

from dataclasses import dataclass

from code_factory.git.models import GitFacts
from code_factory.git.service import GitService
from code_factory.platform.db import UnitOfWork
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.settings.service import SettingsService
from code_factory.stages.service import Ports, StageService
from code_factory.ticket_writes.service import TicketWriteService, WritePorts
from code_factory.tickets.models import TicketAddress
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)
from code_factory.undo.service import UndoService
from stage_fakes import FakeClock, FakeFacts


class FakeGit:
    """Answers the branches it is given; names are judged by git's real naming rule."""

    def __init__(self) -> None:
        self.local: frozenset[str] = frozenset()
        self.remote: frozenset[str] = frozenset()
        self.known = True
        self.default_branch = "main"
        self.calls: list[str] = []

    async def facts(self, repository: str) -> GitFacts:
        self.calls.append(repository)
        return GitFacts(
            default_branch=self.default_branch,
            local=self.local,
            remote=self.remote,
            tips={},
            merged_in=frozenset(),
            log="",
            known=self.known,
        )

    @staticmethod
    def branch_refusal(name: str) -> str | None:
        return GitService.branch_refusal(name)


class RunningOn:
    """The bound check that an agent runs on a ticket: true for the tickets it is given."""

    def __init__(self, *running: str) -> None:
        self.running = set(running)
        self.asked: list[TicketAddress] = []

    async def __call__(self, ref: TicketAddress) -> bool:
        self.asked.append(ref)
        return ref.id in self.running


@dataclass
class Built:
    """The write service and what it is made of, over one unit of work."""

    writes: TicketWriteService
    undo: UndoService
    stages: StageService
    tickets: TicketService
    git: FakeGit


def build(
    uow: UnitOfWork, clock: FakeClock, facts: FakeFacts, *, write_wait: float = 20.0
) -> Built:
    """A fresh write service, undo store and stage service over `uow`."""
    tickets = TicketService(uow, clock=clock)
    stages = StageService(
        uow,
        Ports(
            tickets=tickets,
            reviews=ReviewService(uow, clock=clock),
            activity=ActivityService(uow, clock=clock),
            documents=DocumentService(uow, clock=clock),
            releases=ReleaseService(uow, tickets, clock=clock),
            repositories=RepositoryService(uow),
            settings=SettingsService(uow),
            facts=facts,
        ),
        clock=clock,
    )
    git = FakeGit()
    undo = UndoService(uow, clock)
    ports = WritePorts(tickets=tickets, stages=stages, git=git, repositories=RepositoryService(uow))
    writes = TicketWriteService(uow, ports, undo, clock=clock, write_wait=write_wait)
    return Built(writes, undo, stages, tickets, git)
