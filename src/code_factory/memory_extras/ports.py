"""What memory-extras reads from other modules, as protocols.

`code_factory.memory_extras.module` passes each module's service; a test passes a fake.
"""

import builtins
from pathlib import Path
from typing import Protocol, runtime_checkable

from code_factory.repositories.models import RepositoryRecord
from code_factory.tickets.models import DocHit


@runtime_checkable
class RepositoriesPort(Protocol):
    """The tracked repositories."""

    async def list(self) -> builtins.list[RepositoryRecord]:
        """Every tracked repository, ordered by name."""
        ...

    async def get(self, name: str) -> Path:
        """The main checkout of the repository; raises `NotFoundError` for an unknown one."""
        ...


@runtime_checkable
class TicketsPort(Protocol):
    """The ticket facts the rules need."""

    async def merged(self, repository: str, ids: list[str]) -> frozenset[str]:
        """The ids among `ids` whose work is merged."""
        ...

    async def open_titles(self, repository: str) -> list[tuple[str, str]]:
        """`(id, title)` of each ticket neither archived nor merged."""
        ...

    async def search_documents(self, repository: str, words: list[str], limit: int) -> list[DocHit]:
        """Up to `limit` documents holding every word, in any case."""
        ...
