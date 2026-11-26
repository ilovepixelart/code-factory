"""The memory module's public API: a repository's rules, decisions and lessons.

Each method is one unit of work in its own session. `by` names the actor that records or proposes
an entry (the owner, a run); the owner's other decisions name none, as the stored format keeps none.
An entry is addressed by its repository and its name (`<day>-<slug>`), as the app addresses it.
"""

import builtins
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime

from code_factory.memory.models import (
    Admission,
    EntryImage,
    EntryPatch,
    Intake,
    MemoryEdit,
    MemoryEntry,
    MemoryFields,
    MemoryFilter,
    MemoryStatus,
    NewMemory,
    Preparation,
    Stage,
)
from code_factory.memory.repository import MemoryRepository
from code_factory.memory.rules import (
    check_entry,
    check_new,
    entry_name,
    is_incomplete,
    is_stale,
    matches,
    recall,
    review_due,
)
from code_factory.memory.service.images import apply_patches, record_of, restore_images
from code_factory.memory.tables import MemoryEntryRow
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError

DISMISSED = "dismissed by the owner"
_LIST_FIELDS = ("supersedes", "cites")
_TEXT_FIELDS = ("why", "source", "guard", "scope", "expires", "until")


def utc_now() -> datetime:
    """The service's default clock."""
    return datetime.now(UTC)


def status_of(row: MemoryEntryRow) -> MemoryStatus:
    """Retired once it has a reason; else proposed until approved; else active."""
    if row.retired:
        return "retired"
    return "proposed" if row.proposed else "active"


def to_entry(row: MemoryEntryRow, today: date) -> MemoryEntry:
    """An entry's answer, with the review dates and marks computed for `today`."""
    return MemoryEntry(
        repository=row.repository,
        id=row.name,
        kind=row.kind,  # ty: ignore[invalid-argument-type]  # the check constraint holds it
        statement=row.statement,
        why=row.why,
        source=row.source,
        guard=row.guard,
        scope=row.scope,
        supersedes=row.supersedes,
        expires=row.expires,
        until=row.until_ticket,
        cites=row.cites,
        date=row.written_on,
        reviewed=row.reviewed,
        proposed=row.proposed,
        verdict=row.verdict,
        retired=row.retired,
        merged_into=row.merged_into,
        status=status_of(row),
        review_due=review_due(row.written_on, row.reviewed),
        stale=is_stale(row.written_on, row.reviewed, today),
        incomplete=is_incomplete(row.statement, row.why, row.source),
    )


def _cleaned(fields: MemoryFields) -> MemoryFields:
    values = {name: getattr(fields, name).strip() for name in _TEXT_FIELDS}
    lists = {name: [v.strip() for v in getattr(fields, name) if v.strip()] for name in _LIST_FIELDS}
    return MemoryFields(**values, **lists)


def _flags(keep_both: bool, check_pairs: bool) -> dict[str, bool]:
    return {"keep_both": keep_both, "check_pairs": check_pairs}


def _sources(source: str) -> list[str]:
    return [part.strip() for part in source.split(";") if part.strip()]


class MemoryService:
    """A repository's memory entries."""

    def __init__(self, uow: UnitOfWork, clock: Callable[[], datetime] = utc_now) -> None:
        self._uow = uow
        self._clock = clock
        self._admissions: builtins.list[Admission] = []
        self._preparations: builtins.list[Preparation] = []

    def add_admission(self, check: Admission) -> None:
        """Run `check` on every entry `add` and `propose` write, after the base checks.

        Checks run in the order registered; one that raises refuses the entry and nothing is
        written. They run under a lock on the repository's additions, so a check that reads
        the store sees every earlier write. This is how a module that depends on memory adds its
        rules without memory importing it.
        """
        self._admissions.append(check)

    def add_preparation(self, prepare: Preparation) -> None:
        """Register a check whose slow part runs before the write's transaction opens.

        `prepare` runs once per write, before the repository's additions are locked, so reading
        files or running git holds no connection and no lock; it raises to refuse the entry or
        returns the check that then runs with the registered admissions, under the lock.
        """
        self._preparations.append(prepare)

    def _today(self) -> date:
        return self._clock().astimezone(UTC).date()

    async def add(
        self, new: NewMemory, *, by: str, keep_both: bool = False, check_pairs: bool = False
    ) -> MemoryEntry:
        """Record an entry, dated today; it retires the active entries it supersedes.

        `keep_both` and `check_pairs` are passed to the registered admission checks.
        """
        entry, _ = await self.add_with_images(
            new, by=by, keep_both=keep_both, check_pairs=check_pairs
        )
        return entry

    async def add_with_images(
        self, new: NewMemory, *, by: str, keep_both: bool = False, check_pairs: bool = False
    ) -> tuple[MemoryEntry, builtins.list[EntryImage]]:
        """`add`, and the before-images of every row it wrote: `restore` takes the write back.

        The new entry's image says it was inserted; each entry it retired is imaged as it was.
        """
        intake = Intake(by=by, proposed=False, **_flags(keep_both, check_pairs), now=self._clock())
        return await self._record(new, intake)

    async def propose(
        self, new: NewMemory, *, by: str, keep_both: bool = False, check_pairs: bool = False
    ) -> MemoryEntry:
        """Record an entry held out of every session until the owner approves it.

        Its source is the proposer when it names none; what it supersedes retires on approval.
        """
        intake = Intake(by=by, proposed=True, **_flags(keep_both, check_pairs), now=self._clock())
        entry, _ = await self._record(new, intake)
        return entry

    async def _record(
        self, new: NewMemory, intake: Intake
    ) -> tuple[MemoryEntry, builtins.list[EntryImage]]:
        by, proposed = intake.by, intake.proposed
        fields = _cleaned(new)
        if proposed and not fields.source:
            fields = fields.model_copy(update={"source": by})
        statement = new.statement.strip()
        check_new(statement, fields)
        admitted = new.model_copy(update={"statement": statement, **fields.model_dump()})
        today = self._today()
        checks = [await prepare(admitted, intake) for prepare in self._preparations]
        async with self._uow() as session:
            entries = MemoryRepository(session)
            await entries.lock_additions(new.repository)
            for admit in [*self._admissions, *checks]:
                await admit(admitted, intake)
            name = entry_name(today, statement, await entries.names(new.repository))
            images = await self._supersede(
                entries, new.repository, name, fields.supersedes, retire=not proposed
            )
            values = fields.model_dump(exclude={"until"})
            row = await entries.insert(
                {
                    **values,
                    "until_ticket": fields.until,
                    "repository": new.repository,
                    "name": name,
                    "kind": new.kind,
                    "statement": statement,
                    "proposed": proposed,
                    "written_on": today,
                    "created_by": by,
                    "proposed_by": by if proposed else "",
                    "created_at": self._clock(),
                    "updated_at": self._clock(),
                }
            )
            inserted = EntryImage(
                repository=new.repository, id=name, before=None, updated_at=row.updated_at
            )
            return to_entry(row, today), [inserted, *images]

    async def _supersede(
        self,
        entries: MemoryRepository,
        repository: str,
        by_name: str,
        names: builtins.list[str],
        *,
        retire: bool,
    ) -> builtins.list[EntryImage]:
        """Check each superseded name exists; retire the active ones when `retire`.

        The answer images each entry retired, as it was.
        """
        images: builtins.list[EntryImage] = []
        for name in names:
            if name == by_name:
                raise BadRequestError("an entry cannot supersede itself")
            row = await entries.find(repository, name, for_update=True)
            if row is None:
                msg = f"no entry {name} to supersede in {repository}; name an existing entry"
                raise BadRequestError(msg)
            if retire and not row.retired:
                before = record_of(row)
                row.retired, row.updated_at = f"superseded by {by_name}", self._clock()
                images.append(
                    EntryImage(
                        repository=repository, id=name, before=before, updated_at=row.updated_at
                    )
                )
        return images

    async def get(self, repository: str, name: str) -> MemoryEntry:
        """One entry, retired or not; `NotFoundError` when the repository has none so named."""
        async with self._uow() as session:
            row = await self._find(MemoryRepository(session), repository, name)
            return to_entry(row, self._today())

    async def list(self, where: MemoryFilter | None = None) -> builtins.list[MemoryEntry]:
        """The entries `where` selects (active by default), oldest first."""
        where = where or MemoryFilter()
        async with self._uow() as session:
            rows = await MemoryRepository(session).select(where)
        today = self._today()
        return [to_entry(row, today) for row in rows if status_of(row) == where.status]

    async def list_entries(
        self, repository: str, *, include_retired: bool = False
    ) -> builtins.list[MemoryEntry]:
        """Every entry of the repository, oldest first; the retired ones only when asked.

        Proposals are entries too: they are listed with the active ones.
        """
        async with self._uow() as session:
            rows = await MemoryRepository(session).select(MemoryFilter(repository=repository))
        today = self._today()
        return [to_entry(row, today) for row in rows if include_retired or not row.retired]

    async def search(
        self, query: str, where: MemoryFilter | None = None
    ) -> builtins.list[MemoryEntry]:
        """The entries `where` selects whose name, statement or why hold every word of `query`."""
        found = await self.list(where)
        return [e for e in found if matches(query, e.id, e.statement, e.why)]

    async def edit(self, repository: str, name: str, edit: MemoryEdit) -> MemoryEntry:
        """Change the fields the edit names; the entry counts as reviewed today."""
        changes = edit.model_dump(exclude_none=True)
        async with self._uow() as session:
            row = await self._active(MemoryRepository(session), repository, name)
            for field, value in changes.items():
                stripped = value.strip() if isinstance(value, str) else [v.strip() for v in value]
                setattr(row, field, stripped)
            fields = MemoryFields(why=row.why, source=row.source, guard=row.guard, scope=row.scope)
            check_entry(row.statement, fields.model_copy(update={"supersedes": row.supersedes}))
            row.reviewed, row.updated_at = self._today().isoformat(), self._clock()
            return to_entry(row, self._today())

    async def retire(self, repository: str, name: str, reason: str) -> MemoryEntry:
        """Move an active entry to history with the reason it no longer applies."""
        why = reason.strip()
        if not why or "\n" in why:
            raise BadRequestError("say in one line why it no longer applies")
        async with self._uow() as session:
            row = await self._active(MemoryRepository(session), repository, name)
            row.retired, row.updated_at = why, self._clock()
            return to_entry(row, self._today())

    async def approve(self, repository: str, name: str) -> MemoryEntry:
        """Accept a proposal: sessions load it from now on, and what it supersedes retires."""
        async with self._uow() as session:
            entries = MemoryRepository(session)
            row = await self._proposal(entries, repository, name)
            await self._supersede(entries, repository, name, row.supersedes, retire=True)
            row.proposed, row.reviewed = False, self._today().isoformat()
            row.updated_at = self._clock()
            return to_entry(row, self._today())

    async def dismiss(self, repository: str, name: str) -> MemoryEntry:
        """Decline a proposal: it moves to history as dismissed by the owner."""
        async with self._uow() as session:
            row = await self._proposal(MemoryRepository(session), repository, name)
            row.retired, row.updated_at = DISMISSED, self._clock()
            return to_entry(row, self._today())

    async def merge(self, repository: str, name: str, into: str) -> MemoryEntry:
        """Fold an active entry into another.

        It retires naming the other, which gains each of its sources it does not name already.
        """
        if name == into:
            raise BadRequestError("an entry cannot be merged into itself; name another entry")
        async with self._uow() as session:
            entries = MemoryRepository(session)
            row = await self._active(entries, repository, name)
            target = await self._active(entries, repository, into)
            row.retired, row.merged_into = f'merged into "{target.statement}"', into
            named = _sources(target.source)
            added = [s for s in _sources(row.source) if s not in named]
            target.source = "; ".join([*named, *added])
            row.updated_at = target.updated_at = self._clock()
            return to_entry(row, self._today())

    async def rules_for(self, stage: Stage, repository: str | None = None) -> str:
        """The text a run of `stage` is given: the active entries it loads, one line each."""
        entries = await self.list(MemoryFilter(repository=repository))
        return recall(entries, stage, self._today())

    async def apply(self, patches: Sequence[EntryPatch], *, by: str) -> builtins.list[EntryImage]:
        """Write each patch as given in one unit of work, with no admission check.

        A patch for an entry that exists changes the fields it names; one for a new entry inserts
        it under the id it names. The answer holds one before-image per patch, which `restore`
        takes back.
        """
        context = (by, self._clock(), self._today())
        async with self._uow() as session:
            return await apply_patches(MemoryRepository(session), patches, context)

    async def restore(self, images: Sequence[EntryImage]) -> None:
        """Put the before-images back; `ConflictError` when an entry changed after its image."""
        async with self._uow() as session:
            await restore_images(MemoryRepository(session), images)

    async def count_proposed_by(self, subject: str) -> int:
        """How many entries `subject` proposed, approved or not."""
        async with self._uow() as session:
            return await MemoryRepository(session).count_proposed_by(subject)

    @staticmethod
    async def _find(entries: MemoryRepository, repository: str, name: str) -> MemoryEntryRow:
        row = await entries.find(repository, name, for_update=True)
        if row is None:
            msg = f"{repository} has no memory entry {name}; search its memory to find the name"
            raise NotFoundError(msg)
        return row

    async def _active(
        self, entries: MemoryRepository, repository: str, name: str
    ) -> MemoryEntryRow:
        row = await self._find(entries, repository, name)
        if row.retired:
            raise ConflictError(f"{name} is retired already ({row.retired})")
        return row

    async def _proposal(
        self, entries: MemoryRepository, repository: str, name: str
    ) -> MemoryEntryRow:
        row = await self._active(entries, repository, name)
        if not row.proposed:
            raise ConflictError(f"{name} is not proposed; only a proposal is approved or dismissed")
        return row
