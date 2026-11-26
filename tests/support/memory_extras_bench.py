"""The service under test and everything it was built from, for the memory-extras tests."""

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from code_factory.memory.models import EntryPatch
from code_factory.memory.service import MemoryService
from code_factory.memory_extras.adapters import DefinedTests, OriginWeb, RepositoryFiles
from code_factory.memory_extras.service import MemoryExtrasService
from code_factory.platform.db import UnitOfWork
from memory_extras_fakes import FakeGit, FakeRepositories, FakeTickets
from memory_extras_values import NOW, OWNER


def ticking() -> Callable[[], datetime]:
    """A clock that moves one second on every reading, so two writes never share a moment."""
    moments = iter(NOW + timedelta(seconds=n) for n in range(100_000))
    return lambda: next(moments)


class Bench:
    """The service under test and everything it was built from."""

    def __init__(self, uow: UnitOfWork, base: Path) -> None:
        self.memory = MemoryService(uow, clock=ticking())
        self.git = FakeGit()
        self.tickets = FakeTickets()
        self.repositories = FakeRepositories("sample", "second", base=base)
        self.tests = DefinedTests(self.git)
        self.service = MemoryExtrasService(
            uow,
            self.memory,
            self.tickets,
            self.repositories,
            RepositoryFiles(self.git),
            self.tests,
            OriginWeb(self.git),
            clock=lambda: NOW,
        )
        self.memory.add_preparation(self.service.prepare_admission)

    async def seed(self, entry_id: str, statement: str = "Keep it small", **fields: object) -> str:
        """Write an entry under an explicit id, with no admission check; `date` follows the id."""
        values = {
            "kind": "rule",
            "statement": statement,
            "source": "chat",
            "date": f"{entry_id[:10]}",
            **fields,
        }
        repository = str(values.pop("repository", "sample"))
        await self.memory.apply(
            [EntryPatch(repository=repository, id=entry_id, fields=values)], by=OWNER
        )
        return entry_id


@pytest.fixture
async def bench(uow: UnitOfWork, tmp_path: Path) -> Bench:
    """The service over the isolated database, with git and tickets faked."""
    return Bench(uow, tmp_path)
