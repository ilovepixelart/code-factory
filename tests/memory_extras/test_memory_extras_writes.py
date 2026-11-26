"""The owner's writes: a notice, rows changed in one transaction, and the images that undo them."""

import pytest

from code_factory.memory.models import MemoryEdit, MemoryFilter, NewMemory
from code_factory.memory_extras.models import MemoryChanged
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from memory_extras_bench import Bench
from memory_extras_values import OWNER

REPO = "sample"
OLD = "2026-10-01-merge-at-once"


def draft(statement: str = "Keep it small", **fields: object) -> NewMemory:
    return NewMemory(repository=REPO, kind="rule", statement=statement, source="chat", **fields)  # ty: ignore[invalid-argument-type]


async def rows(bench: Bench) -> dict[str, tuple[str, str]]:
    entries = await bench.memory.list_entries(REPO, include_retired=True)
    return {e.id: (e.statement, e.retired) for e in entries}


async def test_an_added_entry_answers_a_notice_naming_it_and_loads_at_once(bench: Bench) -> None:
    changed = await bench.service.add(draft(), OWNER)
    assert changed.notice == 'Added "Keep it small"'
    (entry,) = await bench.memory.list_entries(REPO)
    assert (entry.id, entry.proposed) == ("2026-11-10-keep-it-small", False)


async def test_a_long_statement_is_cut_to_fifty_characters_in_the_notice(bench: Bench) -> None:
    changed = await bench.service.add(draft("x" * 60), OWNER)
    assert changed.notice == f'Added "{"x" * 49}…"'


async def test_an_add_with_a_blank_source_is_refused_and_writes_nothing(bench: Bench) -> None:
    with pytest.raises(BadRequestError, match=r"^an entry needs a source"):
        await bench.service.add(
            NewMemory(repository=REPO, kind="rule", statement="No source"), OWNER
        )
    assert await rows(bench) == {}


async def test_an_add_to_a_repository_that_is_not_tracked_is_refused(bench: Bench) -> None:
    given = draft().model_copy(update={"repository": "nowhere"})
    with pytest.raises(NotFoundError, match=r"^no such repository$"):
        await bench.service.add(given, OWNER)


async def test_undoing_an_add_removes_the_entry(bench: Bench) -> None:
    changed = await bench.service.add(draft(), OWNER)
    await bench.service.restore(changed.restore)
    assert await rows(bench) == {}


async def test_an_add_that_supersedes_retires_the_old_entry_and_the_undo_puts_both_rows_back(
    bench: Bench,
) -> None:
    await bench.seed(OLD, "Merge each pull request at once")
    changed = await bench.service.add(draft("Land through one queue", supersedes=[OLD]), OWNER)
    after = await rows(bench)
    assert after[OLD][1] == "superseded by 2026-11-10-land-through-one-queue"
    await bench.service.restore(changed.restore)
    assert await rows(bench) == {OLD: ("Merge each pull request at once", "")}


async def test_a_supersession_of_no_entry_is_refused_and_writes_nothing(bench: Bench) -> None:
    await bench.seed(OLD, "Merge each pull request at once")
    given = draft(supersedes=["2026-01-01-nothing"])
    with pytest.raises(BadRequestError, match=r"^no entry 2026-01-01-nothing to supersede$"):
        await bench.service.add(given, OWNER)
    assert await rows(bench) == {OLD: ("Merge each pull request at once", "")}


async def test_the_page_add_does_not_check_pairs(bench: Bench) -> None:
    await bench.service.add(draft("Always rebase ticket branches onto main before landing"), OWNER)
    await bench.service.add(draft("Never rebase ticket branches onto main"), OWNER)
    assert len(await bench.memory.list_entries(REPO)) == 2


async def test_an_edit_changes_the_named_fields_and_marks_the_entry_reviewed(bench: Bench) -> None:
    await bench.seed(OLD, "Merge at once", why="speed")
    changed = await bench.service.edit(REPO, OLD, MemoryEdit(statement=" Merge soon "), OWNER)
    assert changed.notice == f"Saved {OLD}"
    (entry,) = await bench.memory.list_entries(REPO)
    assert (entry.statement, entry.why, entry.reviewed) == ("Merge soon", "speed", "2026-11-10")


async def test_an_empty_edit_only_marks_the_entry_reviewed(bench: Bench) -> None:
    await bench.seed(OLD, "Merge at once")
    changed = await bench.service.edit(REPO, OLD, MemoryEdit(), OWNER)
    assert changed.notice == f"Reviewed {OLD}"
    (entry,) = await bench.memory.list_entries(REPO)
    assert (entry.statement, entry.reviewed) == ("Merge at once", "2026-11-10")


async def test_an_edit_that_leaves_a_blank_statement_or_a_bad_scope_is_refused(
    bench: Bench,
) -> None:
    await bench.seed(OLD, "Merge at once")
    with pytest.raises(BadRequestError, match=r"^an entry needs a statement$"):
        await bench.service.edit(REPO, OLD, MemoryEdit(statement="  "), OWNER)
    with pytest.raises(BadRequestError, match=r"^scope names core"):
        await bench.service.edit(REPO, OLD, MemoryEdit(scope="bulid"), OWNER)
    assert await rows(bench) == {OLD: ("Merge at once", "")}


async def test_an_edit_naming_an_unknown_entry_or_a_retired_one_is_no_such_entry(
    bench: Bench,
) -> None:
    await bench.seed(OLD, "Old", retired="done")
    for missing in ("2026-01-01-none", OLD):
        with pytest.raises(NotFoundError, match=r"^no such entry$"):
            await bench.service.edit(REPO, missing, MemoryEdit(), OWNER)


async def test_an_edit_that_supersedes_retires_the_named_entry_and_refuses_an_unknown_one(
    bench: Bench,
) -> None:
    await bench.seed(OLD, "Merge each pull request at once")
    await bench.seed("2026-10-02-new", "Land through one queue")
    with pytest.raises(BadRequestError, match=r"^no entry 2026-01-01-nothing to supersede$"):
        await bench.service.edit(
            REPO, "2026-10-02-new", MemoryEdit(supersedes=["2026-01-01-nothing"]), OWNER
        )
    assert (await rows(bench))[OLD][1] == ""
    await bench.service.edit(REPO, "2026-10-02-new", MemoryEdit(supersedes=[OLD]), OWNER)
    assert (await rows(bench))[OLD][1] == "superseded by 2026-10-02-new"


async def test_undoing_an_edit_puts_the_entry_back_and_refuses_after_a_later_edit(
    bench: Bench,
) -> None:
    await bench.seed(OLD, "Merge at once")
    first = await bench.service.edit(REPO, OLD, MemoryEdit(statement="First"), OWNER)
    await bench.service.edit(REPO, OLD, MemoryEdit(statement="Second"), OWNER)
    with pytest.raises(ConflictError, match=r"changed since"):
        await bench.service.restore(first.restore)
    assert (await rows(bench))[OLD][0] == "Second"


async def test_undoing_the_latest_edit_restores_the_statement(bench: Bench) -> None:
    await bench.seed(OLD, "Merge at once")
    changed = await bench.service.edit(REPO, OLD, MemoryEdit(statement="First"), OWNER)
    await bench.service.restore(changed.restore)
    assert (await rows(bench))[OLD][0] == "Merge at once"


async def test_a_retirement_names_the_entry_and_records_the_reason(bench: Bench) -> None:
    await bench.seed(OLD, "Merge at once")
    changed = await bench.service.retire(REPO, OLD, " no longer true ", OWNER)
    assert changed.notice == 'Retired "Merge at once"'
    assert (await rows(bench))[OLD][1] == "no longer true"
    await bench.service.restore(changed.restore)
    assert (await rows(bench))[OLD][1] == ""


async def test_a_retirement_needs_one_line_of_reason_and_an_entry_that_is_not_retired(
    bench: Bench,
) -> None:
    await bench.seed(OLD, "Merge at once")
    for reason in ("", "  ", "a\nb"):
        with pytest.raises(BadRequestError, match=r"^say in one line why it no longer applies$"):
            await bench.service.retire(REPO, OLD, reason, OWNER)
    await bench.service.retire(REPO, OLD, "done", OWNER)
    with pytest.raises(BadRequestError, match=rf"^{OLD} is retired already$"):
        await bench.service.retire(REPO, OLD, "done again", OWNER)
    with pytest.raises(NotFoundError, match=r"^no such entry$"):
        await bench.service.retire(REPO, "2026-01-01-none", "done", OWNER)


async def test_a_merge_retires_the_entry_naming_the_target_and_adds_the_sources_it_lacks(
    bench: Bench,
) -> None:
    await bench.seed("2026-10-01-one", "Do it twice", source="chat; CF-1")
    await bench.seed("2026-10-02-two", "Do it once", source="CF-1; owner")
    changed = await bench.service.merge(REPO, "2026-10-01-one", "2026-10-02-two", OWNER)
    assert changed.notice == 'Merged "Do it twice" into "Do it once"'
    entries = {e.id: e for e in await bench.memory.list_entries(REPO, include_retired=True)}
    assert entries["2026-10-01-one"].retired == 'merged into "Do it once"'
    assert entries["2026-10-01-one"].merged_into == "2026-10-02-two"
    assert entries["2026-10-02-two"].source == "CF-1; owner; chat"
    await bench.service.restore(changed.restore)
    again = {e.id: e for e in await bench.memory.list_entries(REPO, include_retired=True)}
    assert (again["2026-10-01-one"].retired, again["2026-10-02-two"].source) == ("", "CF-1; owner")


async def test_a_merge_into_itself_or_into_a_missing_or_retired_entry_is_refused(
    bench: Bench,
) -> None:
    await bench.seed("2026-10-01-one", "One")
    await bench.seed("2026-10-02-gone", "Gone", retired="done")
    with pytest.raises(BadRequestError, match=r"^an entry cannot be merged into itself$"):
        await bench.service.merge(REPO, "2026-10-01-one", "2026-10-01-one", OWNER)
    for target in ("2026-10-02-gone", "2026-12-12-none"):
        with pytest.raises(BadRequestError, match=rf"^no active entry {target}$"):
            await bench.service.merge(REPO, "2026-10-01-one", target, OWNER)
    with pytest.raises(NotFoundError, match=r"^no such entry$"):
        await bench.service.merge(REPO, "2026-12-12-none", "2026-10-01-one", OWNER)


async def test_editing_a_proposal_that_supersedes_retires_nothing_until_it_is_approved(
    bench: Bench,
) -> None:
    await bench.seed(OLD, "Merge each pull request at once")
    await bench.seed("2026-10-02-new", "Land through one queue", proposed=True)
    await bench.service.edit(REPO, "2026-10-02-new", MemoryEdit(supersedes=[OLD]), OWNER)
    assert (await rows(bench))[OLD][1] == ""
    with pytest.raises(BadRequestError, match=r"^no entry 2026-01-01-nothing to supersede$"):
        await bench.service.edit(
            REPO, "2026-10-02-new", MemoryEdit(supersedes=["2026-01-01-nothing"]), OWNER
        )
    await bench.service.approve(REPO, "2026-10-02-new", OWNER)
    assert (await rows(bench))[OLD][1] == "superseded by 2026-10-02-new"


async def test_approving_a_proposal_loads_it_and_retires_what_it_supersedes(bench: Bench) -> None:
    await bench.seed(OLD, "Merge each pull request at once")
    await bench.seed("2026-10-02-new", "Land through one queue", proposed=True, supersedes=[OLD])
    assert (await rows(bench))[OLD][1] == ""
    changed = await bench.service.approve(REPO, "2026-10-02-new", OWNER)
    assert changed.notice == "Approved 2026-10-02-new"
    entries = {e.id: e for e in await bench.memory.list_entries(REPO, include_retired=True)}
    assert (entries["2026-10-02-new"].proposed, entries["2026-10-02-new"].reviewed) == (
        False,
        "2026-11-10",
    )
    assert entries[OLD].retired == "superseded by 2026-10-02-new"
    await bench.service.restore(changed.restore)
    again = {e.id: e for e in await bench.memory.list_entries(REPO, include_retired=True)}
    assert (again["2026-10-02-new"].proposed, again[OLD].retired) == (True, "")


async def test_approving_or_dismissing_an_entry_that_is_not_a_proposal_is_refused(
    bench: Bench,
) -> None:
    await bench.seed(OLD, "Active")
    for action in (bench.service.approve, bench.service.dismiss):
        with pytest.raises(BadRequestError, match=rf"^{OLD} is not proposed$"):
            await action(REPO, OLD, OWNER)


async def test_a_dismissed_proposal_goes_to_history_as_dismissed_by_the_owner(bench: Bench) -> None:
    await bench.seed("2026-10-02-new", "Proposed", proposed=True)
    changed = await bench.service.dismiss(REPO, "2026-10-02-new", OWNER)
    assert changed.notice == "Dismissed 2026-10-02-new"
    assert (await rows(bench))["2026-10-02-new"][1] == "dismissed by the owner"
    assert await bench.memory.list(MemoryFilter(repository=REPO)) == []
    with pytest.raises(NotFoundError, match=r"^no such entry$"):
        await bench.service.approve(REPO, "2026-10-02-new", OWNER)


def test_a_change_answers_its_images_for_the_route_to_keep() -> None:
    assert list(MemoryChanged.model_fields) == ["notice", "restore"]
