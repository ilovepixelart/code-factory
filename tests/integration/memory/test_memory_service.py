"""A repository's memory through the memory service, against the test database.

Names, review dates and retire reasons follow the previous implementation's memory store and its
API golden: `Keep it small and test first`, written on 2026-10-01 from a conversation, is
`2026-10-01-keep-it-small-and-test-first`, due for review on 2026-12-30.
"""

from datetime import date

import pytest

from code_factory.memory.models import MemoryEdit, MemoryFilter, NewMemory
from code_factory.memory.service import MemoryService
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from memory_values import OWNER

REPO = "sample"
KEEP = NewMemory(
    repository=REPO, kind="rule", statement="Keep it small and test first", source="conversation"
)


def rule(statement: str, **fields: object) -> NewMemory:
    return NewMemory.model_validate(
        {"repository": REPO, "kind": "rule", "statement": statement, "source": "chat", **fields}
    )


async def test_an_added_entry_is_named_by_its_day_and_words(memory: MemoryService) -> None:
    added = await memory.add(KEEP, by=OWNER)
    assert added.model_dump(include={"id", "date", "status", "review_due", "incomplete"}) == {
        "id": "2026-10-01-keep-it-small-and-test-first",
        "date": date(2026, 10, 1),
        "status": "active",
        "review_due": "2026-12-30",
        "incomplete": True,
    }
    assert await memory.get(REPO, added.id) == added


async def test_the_same_words_on_the_same_day_get_the_next_number(memory: MemoryService) -> None:
    await memory.add(KEEP, by=OWNER)
    again = await memory.add(KEEP, by=OWNER)
    assert again.id == "2026-10-01-keep-it-small-and-test-first-2"


async def test_an_entry_without_a_source_is_refused(memory: MemoryService) -> None:
    given = rule("No source", source="")
    with pytest.raises(BadRequestError, match="an entry needs a source"):
        await memory.add(given, by=OWNER)


async def test_an_unknown_entry_is_not_found(memory: MemoryService) -> None:
    with pytest.raises(NotFoundError, match="sample has no memory entry 2026-01-01-nothing"):
        await memory.get(REPO, "2026-01-01-nothing")


async def test_an_entry_that_supersedes_another_retires_it(memory: MemoryService) -> None:
    old = await memory.add(rule("Use the old way"), by=OWNER)
    new = await memory.add(rule("Use the new way", supersedes=[old.id]), by=OWNER)
    gone = await memory.get(REPO, old.id)
    assert (gone.status, gone.retired) == ("retired", f"superseded by {new.id}")


async def test_superseding_an_entry_that_does_not_exist_is_refused_and_writes_nothing(
    memory: MemoryService,
) -> None:
    given = rule("Replaces nothing", supersedes=["2026-01-01-nothing"])
    with pytest.raises(BadRequestError, match="no entry 2026-01-01-nothing to supersede"):
        await memory.add(given, by=OWNER)
    assert await memory.search("Replaces nothing") == []


async def test_a_proposal_waits_for_the_owner_and_loads_nowhere(memory: MemoryService) -> None:
    proposal = await memory.propose(
        NewMemory(
            repository=REPO, kind="lesson", statement="Run the gate once", why="It ran twice"
        ),
        by="run-7",
    )
    assert (proposal.status, proposal.proposed, proposal.source) == ("proposed", True, "run-7")
    assert proposal.id not in [e.id for e in await memory.list(MemoryFilter(repository=REPO))]
    assert "Run the gate once" not in await memory.rules_for("build", REPO)


async def test_an_approved_proposal_loads_and_applies_what_it_supersedes(
    memory: MemoryService,
) -> None:
    old = await memory.add(rule("Run the gate twice"), by=OWNER)
    proposal = await memory.propose(rule("Run the gate once", supersedes=[old.id]), by="run-7")
    assert (await memory.get(REPO, old.id)).status == "active"
    approved = await memory.approve(REPO, proposal.id)
    assert (approved.status, approved.reviewed) == ("active", "2026-10-01")
    assert (await memory.get(REPO, old.id)).retired == f"superseded by {proposal.id}"
    assert "- Run the gate once\n" in await memory.rules_for("build", REPO)


async def test_a_dismissed_proposal_retires_and_only_a_proposal_can_be_decided(
    memory: MemoryService,
) -> None:
    proposal = await memory.propose(rule("Guess the answer"), by="run-7")
    dismissed = await memory.dismiss(REPO, proposal.id)
    assert (dismissed.status, dismissed.retired) == ("retired", "dismissed by the owner")
    active = await memory.add(rule("Ask the owner"), by=OWNER)
    with pytest.raises(ConflictError, match=f"{active.id} is not proposed"):
        await memory.approve(REPO, active.id)


async def test_a_search_needs_every_word_and_honours_the_filter(memory: MemoryService) -> None:
    keep = await memory.add(KEEP, by=OWNER)
    await memory.add(rule("Ship small pull requests", repository="other"), by=OWNER)
    assert [e.id for e in await memory.search("keep small")] == [keep.id]
    assert await memory.search("keep gate") == []
    others = await memory.search("small", MemoryFilter(repository="other"))
    assert [e.statement for e in others] == ["Ship small pull requests"]


async def test_an_edit_changes_the_fields_it_names_and_marks_the_entry_reviewed(
    memory: MemoryService,
) -> None:
    added = await memory.add(KEEP, by=OWNER)
    edited = await memory.edit(REPO, added.id, MemoryEdit(why=" Big changes hide bugs "))
    assert (edited.why, edited.statement, edited.reviewed) == (
        "Big changes hide bugs",
        KEEP.statement,
        "2026-10-01",
    )
    assert not edited.incomplete


async def test_a_retired_entry_keeps_its_reason_and_cannot_retire_or_change_again(
    memory: MemoryService,
) -> None:
    added = await memory.add(KEEP, by=OWNER)
    with pytest.raises(BadRequestError, match="say in one line why it no longer applies"):
        await memory.retire(REPO, added.id, " ")
    retired = await memory.retire(REPO, added.id, "the gate enforces it")
    assert (retired.status, retired.retired) == ("retired", "the gate enforces it")
    with pytest.raises(ConflictError, match=f"{added.id} is retired already"):
        await memory.retire(REPO, added.id, "again")
    with pytest.raises(ConflictError, match=f"{added.id} is retired already"):
        await memory.edit(REPO, added.id, MemoryEdit(why="x"))


async def test_a_merge_retires_the_entry_into_another_which_gains_its_sources(
    memory: MemoryService,
) -> None:
    target = await memory.add(rule("Ship small pull requests", source="chat"), by=OWNER)
    folded = await memory.add(rule("Keep diffs small", source="CF-2; chat"), by=OWNER)
    merged = await memory.merge(REPO, folded.id, target.id)
    assert (merged.status, merged.retired, merged.merged_into) == (
        "retired",
        'merged into "Ship small pull requests"',
        target.id,
    )
    assert (await memory.get(REPO, target.id)).source == "chat; CF-2"
    with pytest.raises(BadRequestError, match="an entry cannot be merged into itself"):
        await memory.merge(REPO, target.id, target.id)


async def test_proposals_are_counted_by_who_proposed_them(memory: MemoryService) -> None:
    before = await memory.count_proposed_by("run-count")
    await memory.propose(rule("One"), by="run-count")
    await memory.propose(rule("Two"), by="run-count")
    await memory.add(rule("Three"), by="run-count")
    assert await memory.count_proposed_by("run-count") == before + 2
