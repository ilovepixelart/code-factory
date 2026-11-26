"""What a run is given: applicable entries, the budget cut, the archive index and delivery."""

import hashlib
from pathlib import Path

import pytest

from code_factory.memory_extras.models import Delivery, TicketContext
from code_factory.memory_extras.repository import DeliveryRepository
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import NotFoundError
from memory_extras_bench import Bench
from memory_extras_values import NOW


async def scoped(bench: Bench) -> None:
    await bench.seed("2026-10-01-everywhere", "Applies everywhere")
    await bench.seed("2026-10-02-core", "Applies first", scope="core")
    await bench.seed("2026-10-03-build", "Build runs only", scope="build")
    await bench.seed("2026-10-04-label", "Memory tickets only", scope="label:memory")
    await bench.seed("2026-10-05-docs", "Docs changes only", scope="docs/*.md")
    await bench.seed("2026-10-06-archived", "Searched on demand", scope="archive")


async def ids(bench: Bench, ctx: TicketContext) -> list[str]:
    return [a.entry.id for a in await bench.service.applicable("sample", ctx)]


async def test_a_context_with_nothing_loads_the_entries_that_load_everywhere(bench: Bench) -> None:
    await scoped(bench)
    assert await ids(bench, TicketContext()) == ["2026-10-01-everywhere", "2026-10-02-core"]


async def test_a_stage_loads_the_entries_scoped_to_it_and_not_another_stages(bench: Bench) -> None:
    await scoped(bench)
    assert "2026-10-03-build" in await ids(bench, TicketContext(stage="build"))
    assert "2026-10-03-build" not in await ids(bench, TicketContext(stage="review"))
    assert "2026-10-03-build" not in await ids(bench, TicketContext(stage="merge"))


async def test_a_label_loads_the_entries_for_a_ticket_carrying_it(bench: Bench) -> None:
    await scoped(bench)
    assert "2026-10-04-label" in await ids(bench, TicketContext(labels=("memory",)))
    assert "2026-10-04-label" not in await ids(bench, TicketContext(labels=("web",)))


async def test_a_changed_path_loads_the_entries_whose_glob_it_matches(bench: Bench) -> None:
    await scoped(bench)
    assert "2026-10-05-docs" in await ids(bench, TicketContext(paths=("docs/a/b.md",)))
    assert "2026-10-05-docs" not in await ids(bench, TicketContext(paths=("src/b.py",)))


async def test_an_archived_entry_is_never_applicable_but_is_in_the_index(bench: Bench) -> None:
    await scoped(bench)
    full = TicketContext(stage="build", labels=("memory",), paths=("docs/a.md",))
    assert "2026-10-06-archived" not in await ids(bench, full)
    recall = await bench.service.rules_for("sample", TicketContext())
    assert recall.index == ("- 2026-10-06-archived: Searched on demand",)


async def test_a_proposed_a_superseded_an_ended_and_a_retired_entry_are_not_applicable(
    bench: Bench,
) -> None:
    await bench.seed("2026-10-01-proposed", "Proposed", proposed=True)
    await bench.seed("2026-10-02-old", "Old")
    await bench.seed("2026-10-03-new", "New", supersedes=["2026-10-02-old"])
    await bench.seed("2026-10-04-ended", "Ended", expires="2026-11-09")
    await bench.seed("2026-10-05-until", "Until merged", until="CF-9")
    await bench.seed("2026-10-06-retired", "Retired", retired="no longer true")
    bench.tickets.merged_ids = {"CF-9"}
    assert await ids(bench, TicketContext()) == ["2026-10-03-new"]


async def test_an_entry_expiring_today_is_still_applicable_and_the_next_day_it_is_not(
    bench: Bench,
) -> None:
    await bench.seed("2026-10-01-today", "Today", expires="2026-11-10")
    assert await ids(bench, TicketContext()) == ["2026-10-01-today"]
    assert (
        await bench.service.lapsed("sample", await bench.memory.list_entries("sample"))
        == frozenset()
    )


async def test_lapsed_names_the_entries_that_ended(bench: Bench) -> None:
    await bench.seed("2026-10-04-ended", "Ended", expires="2026-11-09")
    await bench.seed("2026-10-05-until", "Until merged", until="CF-9")
    await bench.seed("2026-10-06-open", "Open")
    bench.tickets.merged_ids = {"CF-9"}
    entries = await bench.memory.list_entries("sample")
    assert await bench.service.lapsed("sample", entries) == {"2026-10-04-ended", "2026-10-05-until"}


async def test_a_lesson_a_test_enforces_is_not_applicable(bench: Bench) -> None:
    bench.git.files = {"tests/test_g.py": "def test_guarded():\n    pass\n"}
    await bench.seed("2026-10-01-enforced", "Enforced", kind="lesson", guard="test_guarded")
    await bench.seed("2026-10-02-missing", "Missing", kind="lesson", guard="test_gone")
    assert await ids(bench, TicketContext()) == ["2026-10-02-missing"]


async def test_the_lines_are_in_load_order_with_the_why_and_the_received_ids_follow_them(
    bench: Bench,
) -> None:
    await bench.seed("2026-10-01-old-lesson", "Old lesson", kind="lesson")
    await bench.seed("2026-11-01-new-lesson", "New lesson", kind="lesson", why="it hurt")
    await bench.seed("2026-10-01-old-rule", "Old rule")
    await bench.seed("2026-09-01-core-lesson", "Core lesson", kind="lesson", scope="core")
    recall = await bench.service.rules_for("sample", TicketContext())
    assert recall.lines == (
        "- Core lesson",
        "- Old rule",
        "- New lesson Why: it hurt",
        "- Old lesson",
    )
    assert recall.received == (
        "2026-09-01-core-lesson",
        "2026-10-01-old-rule",
        "2026-11-01-new-lesson",
        "2026-10-01-old-lesson",
    )
    assert (recall.left_out, recall.overflow_line) == ((), "")


async def test_the_digest_is_the_first_twelve_hex_of_the_sha256_of_the_lines_joined(
    bench: Bench,
) -> None:
    await bench.seed("2026-10-01-a", "First")
    await bench.seed("2026-10-02-b", "Second")
    recall = await bench.service.rules_for("sample", TicketContext())
    assert recall.lines == ("- Second", "- First")
    assert recall.digest == hashlib.sha256(b"- Second\n- First").hexdigest()[:12]


async def test_lessons_past_the_budget_are_left_out_and_not_received(bench: Bench) -> None:
    for day, size in (
        ("2026-11-02", 2001),
        ("2026-11-03", 2000),
        ("2026-11-04", 2000),
        ("2026-11-05", 2000),
    ):
        await bench.seed(f"{day}-lesson", "x" * (size - 3), kind="lesson")
    recall = await bench.service.rules_for("sample", TicketContext())
    assert recall.left_out == ("2026-11-02-lesson",)
    assert "2026-11-02-lesson" not in recall.received
    assert len(recall.received) == 3


async def test_rules_past_the_budget_are_all_kept_and_the_overflow_sentence_is_given(
    bench: Bench,
) -> None:
    for day in ("2026-11-02", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07"):
        await bench.seed(f"{day}-rule", "x" * 1997)
    recall = await bench.service.rules_for("sample", TicketContext())
    assert len(recall.lines) == 5
    assert recall.overflow_line == (
        "The rules and decisions above take 2,000 characters over the memory budget of 8,000: "
        "ask the owner to merge, scope or retire one."
    )


async def test_an_entry_citing_what_is_gone_carries_a_stale_mark_that_counts_against_the_budget(
    bench: Bench, tmp_path: Path
) -> None:
    (tmp_path / "sample").mkdir()
    await bench.seed("2026-11-01-cites", "Cites things", cites=["gone.py"])
    recall = await bench.service.rules_for("sample", TicketContext())
    assert recall.lines == ("- Cites things [stale: cites gone.py no longer exist]",)
    applicable = await bench.service.applicable("sample", TicketContext())
    assert applicable[0].mark == " [stale: cites gone.py no longer exist]"


async def test_delivery_records_what_was_given_and_what_was_cut_and_a_repeat_adds_nothing(
    bench: Bench, uow: UnitOfWork
) -> None:
    for day, size in (
        ("2026-11-02", 2001),
        ("2026-11-03", 2000),
        ("2026-11-04", 2000),
        ("2026-11-05", 2000),
    ):
        await bench.seed(f"{day}-lesson", "x" * (size - 3), kind="lesson")
    first = await bench.service.deliver("run-1", "CF-1", "sample", TicketContext(), now=NOW)
    again = await bench.service.deliver("run-1", "CF-1", "sample", TicketContext(), now=NOW)
    assert first == again
    async with uow() as session:
        stored = await DeliveryRepository(session).of_run("run-1")
    assert stored == [
        Delivery(entry_id="2026-11-02-lesson", left_out=True),
        Delivery(entry_id="2026-11-03-lesson"),
        Delivery(entry_id="2026-11-04-lesson"),
        Delivery(entry_id="2026-11-05-lesson"),
    ]


async def test_delivering_to_an_unknown_repository_is_refused_and_stores_nothing(
    bench: Bench, uow: UnitOfWork
) -> None:
    with pytest.raises(NotFoundError, match=r"unknown repository"):
        await bench.service.deliver("run-9", "CF-1", "nowhere", TicketContext(), now=NOW)
    async with uow() as session:
        assert await DeliveryRepository(session).of_run("run-9") == []
