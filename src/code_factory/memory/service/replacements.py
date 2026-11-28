"""Transactional replacements of one Memory entry by another."""

import builtins
from datetime import datetime

from code_factory.memory.models import EntryImage, MemoryEntry
from code_factory.memory.repository import MemoryRepository
from code_factory.memory.service.entries import Entries, to_entry
from code_factory.memory.service.images import record_of
from code_factory.memory.tables import MemoryEntryRow
from code_factory.platform.errors import BadRequestError, ConflictError


def _sources(source: str) -> list[str]:
    return [part.strip() for part in source.split(";") if part.strip()]


def _images(repository: str, locked: dict[str, MemoryEntryRow], now: datetime) -> list[EntryImage]:
    return [
        EntryImage(repository=repository, id=key, before=record_of(row), updated_at=now)
        for key, row in locked.items()
    ]


class MemoryService(Entries):
    """The Memory store, including changes that keep one of two entries."""

    async def merge(self, repository: str, name: str, into: str) -> MemoryEntry:
        """Fold an active entry into another, which gains its sources."""
        source, _, _ = await self.merge_with_images(repository, name, into)
        return source

    async def merge_with_images(
        self, repository: str, name: str, into: str
    ) -> tuple[MemoryEntry, MemoryEntry, builtins.list[EntryImage]]:
        """Fold an entry and return both entries and their before-images."""
        if name == into:
            raise BadRequestError("an entry cannot be merged into itself; name another entry")
        async with self._uow() as session:
            locked = await self._active_pair(MemoryRepository(session), repository, name, into)
            row, target = locked[name], locked[into]
            now = self._clock()
            images = _images(repository, locked, now)
            row.retired, row.merged_into = f'merged into "{target.statement}"', into
            named = _sources(target.source)
            added = [s for s in _sources(row.source) if s not in named]
            target.source = "; ".join([*named, *added])
            row.updated_at = target.updated_at = now
            today = self._today()
            return to_entry(row, today), to_entry(target, today), images

    async def supersede(
        self, repository: str, name: str, older: str
    ) -> tuple[MemoryEntry, MemoryEntry, builtins.list[EntryImage]]:
        """Retire the older entry and capture both before-images."""
        if name == older:
            raise BadRequestError("an entry cannot supersede itself")
        async with self._uow() as session:
            locked = await self._active_pair(MemoryRepository(session), repository, name, older)
            replacement, previous = locked[name], locked[older]
            if replacement.proposed or previous.proposed:
                raise ConflictError("only approved memory entries can supersede one another")
            now, today = self._clock(), self._today()
            images = _images(repository, locked, now)
            replacement.supersedes = list(dict.fromkeys([*replacement.supersedes, older]))
            replacement.reviewed = today.isoformat()
            previous.retired = f"superseded by {name}"
            replacement.updated_at = previous.updated_at = now
            return to_entry(replacement, today), to_entry(previous, today), images

    async def _active_pair(
        self, entries: MemoryRepository, repository: str, first: str, second: str
    ) -> dict[str, MemoryEntryRow]:
        """Use the same lock order for both directions of the change."""
        return {
            key: await self._active(entries, repository, key) for key in sorted((first, second))
        }
