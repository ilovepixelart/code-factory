"""Fakes of what memory-extras reads from git, tickets and the tracked repositories."""

import asyncio
import builtins
import re
from pathlib import Path

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.platform.text import name_matches
from code_factory.repositories.models import RepositoryRecord
from code_factory.tickets.models import DocHit, DocumentName


class FakeGit:
    """A main checkout held in a dict: path to text. Every call is counted."""

    def __init__(self, files: dict[str, str] | None = None, head: str = "c1") -> None:
        self.files = files or {}
        self.head = head
        self.remote: str | None = None
        self.calls: dict[str, int] = {}
        self.fail: Exception | None = None
        self.unreadable: set[str] = set()

    def _count(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1
        if self.fail is not None:
            raise self.fail

    async def head_commit(self, repository: str) -> str:  # noqa: ARG002
        self._count("head_commit")
        return self.head

    async def tracked_files(
        self,
        repository: str,
        patterns: builtins.list[str] | None = None,
    ) -> builtins.list[str]:
        self._count("tracked_files")
        _ = repository
        await asyncio.sleep(0)
        wanted = patterns or ["*"]
        return [path for path in self.files if any(name_matches(path, p) for p in wanted)]

    async def read_text_below(self, root: Path, relative: str, limit: int) -> str | None:  # noqa: ARG002
        self._count("read_text_below")
        if relative in self.unreadable:
            msg = f"{relative} is not a regular file"
            raise BadRequestError(msg)
        return self.files.get(relative)

    async def remote_url(self, repository: str) -> str | None:  # noqa: ARG002
        self._count("remote_url")
        return self.remote


class FakeRepositories:
    """Tracked repositories by name, each at `<base>/<name>`."""

    def __init__(self, *names: str, base: Path = Path("/repos")) -> None:
        self.names = names
        self.base = base

    async def list(self) -> builtins.list[RepositoryRecord]:
        return [RepositoryRecord(name=n, path=str(self.base / n)) for n in sorted(self.names)]

    async def get(self, name: str) -> Path:
        if name not in self.names:
            msg = "unknown repository"
            raise NotFoundError(msg)
        return self.base / name


class FakeTickets:
    """Ticket facts: merged ids, open titles and ticket documents, per repository."""

    def __init__(self) -> None:
        self.merged_ids: set[str] = set()
        self.titles: dict[str, builtins.list[tuple[str, str]]] = {}
        self.documents: dict[str, builtins.list[tuple[str, str, str]]] = {}

    async def merged(self, repository: str, ids: builtins.list[str]) -> frozenset[str]:  # noqa: ARG002
        for ticket in ids:  # the real service refuses what is no ticket id
            if not re.fullmatch(r"CF-[1-9][0-9]*", ticket):
                msg = f"{ticket!r} is not a ticket id CF-<n>"
                raise BadRequestError(msg)
        return frozenset(i for i in ids if i in self.merged_ids)

    async def open_titles(self, repository: str) -> builtins.list[tuple[str, str]]:
        return self.titles.get(repository, [])

    async def search_documents(
        self, repository: str, words: builtins.list[str], limit: int
    ) -> builtins.list[DocHit]:
        found = [
            DocHit(ticket_id=ticket, name=DocumentName(name), text=text)
            for ticket, name, text in self.documents.get(repository, [])
            if all(word in text.lower() for word in words)
        ]
        return found[:limit]
