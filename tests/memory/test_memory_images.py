"""Applying patches to entries and putting the before-images back (the undo of a memory write).

Expected values are worked by hand from the memory-extras contract: `apply` writes explicit
entries in one transaction and answers one before-image per patch (`before` is `None` for an
insert); `restore` writes the images back, and refuses when a row changed after the image.
"""

from datetime import date, datetime, timedelta

import pytest

from code_factory.memory.models import EntryPatch, MemoryEdit, NewMemory
from code_factory.memory.service import MemoryService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, ConflictError
from memory_values import NOW, OWNER

REPO = "sample"
OLD = "2026-09-01-keep-it-small"


def _ticking(start: datetime):  # noqa: ANN202
    moments = iter(start + timedelta(seconds=n) for n in range(1000))
    return lambda: next(moments)


def explicit(name: str, **fields: object) -> EntryPatch:
    values = {
        "kind": "rule",
        "statement": "Keep it small",
        "source": "chat",
        "date": date(2026, 9, 1),
        **fields,
    }
    return EntryPatch(repository=REPO, id=name, fields=values)


async def test_an_applied_patch_writes_the_entry_under_its_explicit_id(
    memory: MemoryService,
) -> None:
    images = await memory.apply([explicit(OLD, why="size")], by=OWNER)
    entry = await memory.get(REPO, OLD)
    assert (entry.statement, entry.why, entry.date, entry.status) == (
        "Keep it small",
        "size",
        date(2026, 9, 1),
        "active",
    )
    assert [(i.repository, i.id, i.before) for i in images] == [(REPO, OLD, None)]


async def test_an_applied_patch_changes_only_the_fields_it_names(memory: MemoryService) -> None:
    await memory.apply([explicit(OLD, why="size")], by=OWNER)
    images = await memory.apply(
        [EntryPatch(repository=REPO, id=OLD, fields={"statement": "Keep it tiny"})], by=OWNER
    )
    entry = await memory.get(REPO, OLD)
    assert (entry.statement, entry.why, entry.source) == ("Keep it tiny", "size", "chat")
    assert images[0].before is not None
    assert images[0].before.statement == "Keep it small"


async def test_a_patch_applies_no_admission_check(memory: MemoryService) -> None:
    async def refuse(*_: object) -> None:
        raise ConflictError("refused")

    memory.add_admission(refuse)
    await memory.apply([explicit(OLD)], by=OWNER)
    assert (await memory.get(REPO, OLD)).statement == "Keep it small"


async def test_one_bad_patch_leaves_every_row_as_it_was(memory: MemoryService) -> None:
    good = explicit(OLD)
    bad = EntryPatch(repository=REPO, id="2026-09-02-other", fields={"statement": "no kind"})
    with pytest.raises(BadRequestError, match="2026-09-02-other"):
        await memory.apply([good, bad], by=OWNER)
    assert await memory.list_entries(REPO) == []


async def test_a_patch_names_only_fields_an_entry_has(memory: MemoryService) -> None:
    given = [explicit(OLD, wobble="x")]
    with pytest.raises(BadRequestError, match="no field wobble"):
        await memory.apply(given, by=OWNER)


async def test_restoring_an_insert_deletes_the_row(memory: MemoryService) -> None:
    images = await memory.apply([explicit(OLD)], by=OWNER)
    await memory.restore(images)
    assert await memory.list_entries(REPO, include_retired=True) == []


async def test_restoring_an_update_puts_the_earlier_values_back(uow: UnitOfWork) -> None:
    memory = MemoryService(uow, clock=_ticking(NOW))
    await memory.apply([explicit(OLD, why="size")], by=OWNER)
    images = await memory.apply(
        [EntryPatch(repository=REPO, id=OLD, fields={"retired": "gone", "why": "other"})], by=OWNER
    )
    await memory.restore(images)
    entry = await memory.get(REPO, OLD)
    assert (entry.status, entry.why, entry.retired) == ("active", "size", "")


async def test_restore_is_refused_once_the_row_changed_after_the_image(uow: UnitOfWork) -> None:
    memory = MemoryService(uow, clock=_ticking(NOW))
    images = await memory.apply([explicit(OLD)], by=OWNER)
    await memory.edit(REPO, OLD, MemoryEdit(statement="Edited meanwhile"))
    with pytest.raises(ConflictError, match=f"{OLD} changed since"):
        await memory.restore(images)
    assert (await memory.get(REPO, OLD)).statement == "Edited meanwhile"


async def test_restore_is_refused_when_the_row_is_gone(uow: UnitOfWork) -> None:
    memory = MemoryService(uow, clock=_ticking(NOW))
    images = await memory.apply([explicit(OLD)], by=OWNER)
    await memory.restore(images)
    with pytest.raises(ConflictError, match=f"{OLD} changed since"):
        await memory.restore(images)


async def test_listed_entries_hide_the_retired_unless_asked(memory: MemoryService) -> None:
    keep = await memory.add(
        NewMemory(repository=REPO, kind="rule", statement="Keep", source="chat"), by=OWNER
    )
    drop = await memory.add(
        NewMemory(repository=REPO, kind="rule", statement="Drop", source="chat"), by=OWNER
    )
    await memory.retire(REPO, drop.id, "no longer true")
    assert [e.id for e in await memory.list_entries(REPO)] == [keep.id]
    assert {e.id for e in await memory.list_entries(REPO, include_retired=True)} == {
        keep.id,
        drop.id,
    }
    assert await memory.list_entries("elsewhere") == []


async def test_restore_is_refused_once_a_later_write_retired_the_entry(uow: UnitOfWork) -> None:
    memory = MemoryService(uow, clock=_ticking(NOW))
    images = await memory.apply([explicit(OLD)], by=OWNER)
    await memory.add(
        NewMemory(
            repository=REPO,
            kind="rule",
            statement="Keep it tiny",
            source="chat",
            supersedes=[OLD],
        ),
        by=OWNER,
    )
    with pytest.raises(ConflictError, match=f"{OLD} changed since"):
        await memory.restore(images)
    assert (await memory.get(REPO, OLD)).status == "retired"


async def test_a_proposed_entry_inserted_by_a_patch_is_counted_for_its_proposer(
    memory: MemoryService,
) -> None:
    await memory.apply([explicit(OLD, proposed=True)], by="run-1")
    await memory.apply([explicit("2026-09-02-other")], by="run-2")
    assert await memory.count_proposed_by("run-1") == 1
    assert await memory.count_proposed_by("run-2") == 0
