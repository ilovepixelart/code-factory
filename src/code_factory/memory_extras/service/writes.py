"""The owner's changes to the Memory page, each answering a notice and what undoes it."""

from datetime import datetime
from typing import Any

from code_factory.memory.models import EntryPatch, MemoryEdit, MemoryEntry, NewMemory
from code_factory.memory_extras.models import MemoryChanged, Restore
from code_factory.memory_extras.rules import (
    approved,
    dismissed,
    edited,
    merge_patches,
    named,
    plan_supersession,
    retirement,
    superseded_reason,
)
from code_factory.memory_extras.service.admission import AdmissionMixin
from code_factory.platform.errors import BadRequestError, NotFoundError


class WritesMixin(AdmissionMixin):
    """Add, edit, retire, merge, approve, dismiss and undo."""

    async def _find(self, repository: str, entry_id: str) -> MemoryEntry:
        for entry in await self._memory.list_entries(repository, include_retired=True):
            if entry.id == entry_id:
                return entry
        msg = "no such entry"
        raise NotFoundError(msg)

    async def _active(self, repository: str, entry_id: str) -> MemoryEntry:
        entry = await self._find(repository, entry_id)
        if entry.retired:
            msg = "no such entry"
            raise NotFoundError(msg)
        return entry

    async def _apply(self, patches: list[EntryPatch], notice: str, by: str) -> MemoryChanged:
        images = await self._memory.apply(patches, by=by)
        return MemoryChanged(notice=notice, restore=Restore(images=tuple(images)))

    async def _supersession(self, entry: MemoryEntry, names: list[str]) -> list[EntryPatch]:
        """The patches that retire what `entry` supersedes; none while it is a proposal."""
        entries = await self._memory.list_entries(entry.repository, include_retired=True)
        active = {e.id for e in entries if not e.retired}
        retired = {e.id for e in entries if e.retired}
        if entry.proposed:
            plan_supersession(entry.id, names, active, retired)
            return []
        return [
            EntryPatch(
                repository=entry.repository,
                id=name,
                fields={"retired": superseded_reason(entry.id)},
            )
            for name in plan_supersession(entry.id, names, active, retired)
        ]

    def _patch(self, entry: MemoryEntry, fields: dict[str, Any]) -> EntryPatch:
        return EntryPatch(repository=entry.repository, id=entry.id, fields=fields)

    async def add(self, draft: NewMemory, by: str) -> MemoryChanged:
        """Record an entry that loads at once; what it supersedes retires with it.

        Raises:
            NotFoundError: The repository is not tracked.
            BadRequestError: An admission check refuses the entry.
        """
        if draft.repository not in {r.name for r in await self._repositories.list()}:
            msg = "no such repository"
            raise NotFoundError(msg)
        entry, images = await self._memory.add_with_images(draft, by=by)
        return MemoryChanged(
            notice=f"Added {named(entry.statement)}", restore=Restore(images=tuple(images))
        )

    async def edit(
        self, repository: str, entry_id: str, edit: MemoryEdit, by: str, now: datetime | None = None
    ) -> MemoryChanged:
        """Change the named fields and mark the entry reviewed; an empty edit only reviews it."""
        entry = await self._active(repository, entry_id)
        fields = edited(entry, edit, self._today(now))
        after = entry.model_copy(update=fields)
        patches = [self._patch(entry, fields), *await self._supersession(after, after.supersedes)]
        verb = "Saved" if edit.model_dump(exclude_none=True) else "Reviewed"
        return await self._apply(patches, f"{verb} {entry_id}", by)

    async def retire(self, repository: str, entry_id: str, reason: str, by: str) -> MemoryChanged:
        """Move an active entry to History with the reason it no longer applies."""
        entry = await self._find(repository, entry_id)
        said = retirement(entry, reason)
        return await self._apply(
            [self._patch(entry, {"retired": said})], f"Retired {named(entry.statement)}", by
        )

    async def merge(self, repository: str, entry_id: str, into: str, by: str) -> MemoryChanged:
        """Fold an entry into another: it retires naming it, and the other gains its sources."""
        entry = await self._find(repository, entry_id)
        if into == entry_id:
            msg = "an entry cannot be merged into itself"
            raise BadRequestError(msg)
        try:
            target = await self._active(repository, into)
        except NotFoundError:
            msg = f"no active entry {into}"
            raise BadRequestError(msg) from None
        retirement(entry, "merged")
        steps = merge_patches(entry, target)
        patches = [self._patch(entry, steps.retired)]
        if steps.target is not None:
            patches.append(self._patch(target, steps.target))
        notice = f"Merged {named(entry.statement)} into {named(target.statement)}"
        return await self._apply(patches, notice, by)

    async def approve(
        self, repository: str, entry_id: str, by: str, now: datetime | None = None
    ) -> MemoryChanged:
        """Accept a proposal: sessions load it from now on, and what it supersedes retires."""
        entry = await self._active(repository, entry_id)
        fields = approved(entry, self._today(now))
        after = entry.model_copy(update=fields)
        patches = [self._patch(entry, fields), *await self._supersession(after, after.supersedes)]
        return await self._apply(patches, f"Approved {entry_id}", by)

    async def dismiss(self, repository: str, entry_id: str, by: str) -> MemoryChanged:
        """Decline a proposal: it moves to History as dismissed by the owner."""
        entry = await self._active(repository, entry_id)
        return await self._apply(
            [self._patch(entry, dismissed(entry))], f"Dismissed {entry_id}", by
        )

    async def restore(self, restore: Restore) -> None:
        """Put the rows of a change back; `ConflictError` when one changed since."""
        await self._memory.restore(list(restore.images))
