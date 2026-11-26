"""`add_with_images` records an entry like `add` and answers the images that undo the write."""

import pytest

from code_factory.memory.models import MemoryFilter, NewMemory
from code_factory.memory.service import MemoryService
from code_factory.platform.errors import BadRequestError
from memory_values import OWNER

REPO = "sample"


def draft(statement: str, **fields: object) -> NewMemory:
    return NewMemory(repository=REPO, kind="rule", statement=statement, source="chat", **fields)  # ty: ignore[invalid-argument-type]


async def test_an_added_entry_comes_with_an_image_saying_it_was_inserted(
    memory: MemoryService,
) -> None:
    entry, images = await memory.add_with_images(draft("Keep it small"), by=OWNER)
    assert [(i.repository, i.id, i.before) for i in images] == [(REPO, entry.id, None)]


async def test_restoring_the_images_of_an_add_removes_the_entry(memory: MemoryService) -> None:
    _, images = await memory.add_with_images(draft("Keep it small"), by=OWNER)
    await memory.restore(images)
    assert await memory.list_entries(REPO, include_retired=True) == []


async def test_an_add_that_supersedes_images_the_retired_entry_as_it_was(
    memory: MemoryService,
) -> None:
    old = await memory.add(draft("Merge each pull request at once"), by=OWNER)
    new, images = await memory.add_with_images(
        draft("Land through one queue", supersedes=[old.id]), by=OWNER
    )
    assert {i.id for i in images} == {old.id, new.id}
    retired = await memory.get(REPO, old.id)
    assert retired.retired == f"superseded by {new.id}"
    before = next(i.before for i in images if i.id == old.id)
    assert before is not None
    assert before.retired == ""
    await memory.restore(images)
    assert [e.id for e in await memory.list(MemoryFilter(repository=REPO))] == [old.id]


async def test_a_refused_add_answers_no_images(memory: MemoryService) -> None:
    with pytest.raises(BadRequestError, match="needs a source"):
        await memory.add_with_images(
            NewMemory(repository=REPO, kind="rule", statement="No source"), by=OWNER
        )
