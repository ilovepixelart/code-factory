"""What every use case of the service shares.

The clock, the collaborators and one read of a repository's entries.
"""

import builtins
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from code_factory.memory.models import MemoryEntry
from code_factory.memory.service import MemoryService
from code_factory.memory_extras.adapters import DefinedTests, OriginWeb, RepositoryFiles
from code_factory.memory_extras.ports import RepositoriesPort, TicketsPort
from code_factory.memory_extras.rules import gone_cites, is_ticket_id, lapsed, superseded
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import NotFoundError
from code_factory.platform.text import day_text, epoch_day


def utc_now() -> datetime:
    """The service's default clock."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class View:
    """A repository's entries and what is known of them, read once.

    `entries` holds every entry, retired ones too. `current` are the active entries (proposals
    included) that have not ended. `gone` names, for each current entry, the cites that no longer
    exist; it is empty until `Collaborators.with_cites` fills it.
    """

    repository: str
    entries: builtins.list[MemoryEntry]
    current: builtins.list[MemoryEntry]
    ended: frozenset[str]
    defined: frozenset[str]
    replaced: dict[str, str]
    gone: dict[str, builtins.list[str]]

    @property
    def retired(self) -> builtins.list[MemoryEntry]:
        """The entries with a reason to be in History."""
        return [entry for entry in self.entries if entry.retired]


class Collaborators:
    """The clock, the memory service, the ports and the adapters."""

    def __init__(  # noqa: PLR0913, PLR0917  # the service's collaborators, each read through one
        self,
        uow: UnitOfWork,
        memory: MemoryService,
        tickets: TicketsPort,
        repositories: RepositoriesPort,
        files: RepositoryFiles,
        tests: DefinedTests,
        origin: OriginWeb,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow = uow
        self._memory = memory
        self._tickets = tickets
        self._repositories = repositories
        self._files = files
        self._tests = tests
        self._origin = origin
        self._clock = clock

    def _day(self, now: datetime | None = None) -> int:
        return epoch_day(now or self._clock())

    def _today(self, now: datetime | None = None) -> str:
        return day_text(self._day(now))

    async def _root(self, repository: str) -> Path:
        return await self._repositories.get(repository)

    async def _root_if_tracked(self, repository: str) -> Path | None:
        """The main checkout, or None for a repository nobody tracks (its entries are rows only)."""
        try:
            return await self._root(repository)
        except NotFoundError:
            return None

    async def _ended(
        self, repository: str, active: builtins.list[MemoryEntry], today: str
    ) -> frozenset[str]:
        until = sorted({e.until.strip() for e in active if is_ticket_id(e.until.strip())})
        merged = await self._tickets.merged(repository, until) if until else frozenset()
        return frozenset(e.id for e in active if lapsed(e, today, merged.__contains__))

    async def _defined(self, repository: str, active: builtins.list[MemoryEntry]) -> frozenset[str]:
        if not any(e.guard.strip() or e.cites for e in active):
            return frozenset()
        root = await self._root_if_tracked(repository)
        return frozenset() if root is None else await self._tests.defined(repository, root)

    async def _view(
        self, repository: str, now: datetime | None = None, defined: frozenset[str] | None = None
    ) -> View:
        """Read the entries of the repository, then what the facts say of them.

        `defined` is the tests already found for the repository; without it they are looked up.
        """
        entries = await self._memory.list_entries(repository, include_retired=True)
        return await self._view_of(repository, entries, now, defined)

    async def _view_of(
        self,
        repository: str,
        entries: builtins.list[MemoryEntry],
        now: datetime | None,
        defined: frozenset[str] | None = None,
    ) -> View:
        active = [e for e in entries if not e.retired]
        ended = await self._ended(repository, active, self._today(now))
        if defined is None:
            defined = await self._defined(repository, active)
        current = [e for e in active if e.id not in ended]
        return View(repository, entries, current, ended, defined, superseded(entries), {})

    async def with_cites(self, view: View) -> View:
        """The view with the cites that are gone named for each current entry."""
        cites = [cite for entry in view.current for cite in entry.cites]
        exists = await self._files.cites_exist(await self._root(view.repository), cites)
        gone = {
            entry.id: found
            for entry in view.current
            if (found := gone_cites(entry, view.defined, exists.__contains__))
        }
        return View(
            view.repository,
            view.entries,
            view.current,
            view.ended,
            view.defined,
            view.replaced,
            gone,
        )
