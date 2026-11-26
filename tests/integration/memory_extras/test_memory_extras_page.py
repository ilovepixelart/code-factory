"""The Memory page over real memory rows: lists, History, left-out, queue and delivery counts."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from code_factory.memory_extras.models import TicketContext
from code_factory.platform.errors import NotFoundError
from memory_extras_bench import Bench
from memory_extras_values import NOW

PAGE_KEYS = [
    "repositories", "unreviewed", "rules", "decisions", "lessons", "retired", "loaded_chars",
    "ceiling", "rules_over", "left_out", "pairs", "unreadable", "results", "matched", "page",
    "size", "proposals", "review_queue", "filing",
]  # fmt: skip
RECORD_KEYS = [
    "id", "kind", "date", "source", "statement", "why", "guard", "repository", "reviewed",
    "guard_state", "loaded", "left_out", "superseded_by", "scope", "supersedes", "loads", "chars",
    "proposed", "stale", "incomplete", "review_due", "filing", "cites", "stale_cites",
    "received_by", "received_count", "last_received", "unused",
]  # fmt: skip
EARLY = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


async def sample_entries(bench: Bench) -> None:
    await bench.seed(
        "2026-10-01-keep-it-small", "Keep it small and test first", source="conversation"
    )
    await bench.seed(
        "2026-10-02-the-gate-ran-twice",
        "The gate ran twice on one tree",
        kind="lesson",
        source="CF-2",
    )
    await bench.seed("2026-10-03-ship-small", "Ship small pull requests", kind="decision")


async def test_the_page_has_the_previous_answers_keys_in_its_order(bench: Bench) -> None:
    page = await bench.service.page("")
    assert list(page.model_dump()) == PAGE_KEYS
    assert page.repositories == ["sample", "second"]
    assert (page.ceiling, page.page, page.size, page.matched, page.unreadable) == (
        8000,
        1,
        50,
        0,
        [],
    )


async def test_the_records_of_the_sample_are_the_previous_golden_records(bench: Bench) -> None:
    await sample_entries(bench)
    page = await bench.service.page("", now=EARLY)
    records = [r.model_dump() for r in page.unreviewed]
    assert [list(r) for r in records] == [RECORD_KEYS] * 3
    golden = [
        ("2026-10-01-keep-it-small", "rule", "conversation", "Keep it small and test first", ""),
        (
            "2026-10-02-the-gate-ran-twice",
            "lesson",
            "CF-2",
            "The gate ran twice on one tree",
            "none",
        ),
        ("2026-10-03-ship-small", "decision", "chat", "Ship small pull requests", ""),
    ]
    sizes = [(31, "2026-12-30"), (33, "2026-12-31"), (27, "2027-01-01")]
    for record, (id_, kind, source, statement, guard_state), (chars, due) in zip(
        records, golden, sizes, strict=True
    ):
        assert record == {
            "id": id_, "kind": kind, "date": id_[:10], "source": source, "statement": statement,
            "why": "", "guard": "", "repository": "sample", "reviewed": "",
            "guard_state": guard_state, "loaded": True, "left_out": False, "superseded_by": "",
            "scope": "", "supersedes": "", "loads": "every session", "chars": chars,
            "proposed": False, "stale": False, "incomplete": True, "review_due": due,
            "filing": "committed", "cites": "", "stale_cites": [], "received_by": [],
            "received_count": 0, "last_received": "", "unused": False,
        }  # fmt: skip
    assert (page.rules, page.decisions, page.lessons, page.retired) == ([], [], [], [])
    assert page.loaded_chars == 91


async def test_a_reviewed_entry_is_listed_under_its_kind(bench: Bench) -> None:
    await bench.seed("2026-10-01-a", "A rule", reviewed="2026-10-02")
    await bench.seed("2026-10-01-b", "A decision", kind="decision", reviewed="2026-10-02")
    await bench.seed("2026-10-01-c", "A lesson", kind="lesson", reviewed="2026-10-02")
    page = await bench.service.page("", now=EARLY)
    assert [r.id for r in page.rules] == ["2026-10-01-a"]
    assert [r.id for r in page.decisions] == ["2026-10-01-b"]
    assert [r.id for r in page.lessons] == ["2026-10-01-c"]
    assert page.unreviewed == []


async def test_an_entry_that_expired_is_under_retired_with_its_day(bench: Bench) -> None:
    await bench.seed("2026-10-01-ends", "Ends", expires="2026-11-09")
    await bench.seed("2026-10-01-lasts", "Lasts", expires="2026-11-10")
    page = await bench.service.page("")
    assert [(h.id, h.retired, h.merged_into) for h in page.retired] == [
        ("2026-10-01-ends", "expired 2026-11-09", "")
    ]
    assert [r.id for r in page.unreviewed] == ["2026-10-01-lasts"]


async def test_an_entry_stored_with_an_until_that_is_no_ticket_id_never_ends(bench: Bench) -> None:
    await bench.seed("2026-10-01-typo", "Typo", until="CF-typo")
    await bench.seed("2026-10-01-ends", "Ends", until="CF-9")
    bench.tickets.merged_ids = {"CF-9"}
    page = await bench.service.page("")
    assert [h.id for h in page.retired] == ["2026-10-01-ends"]


async def test_an_entry_ends_when_its_until_ticket_merged(bench: Bench) -> None:
    await bench.seed("2026-10-01-ends", "Ends", until="CF-9")
    await bench.seed("2026-10-01-waits", "Waits", until="CF-8")
    bench.tickets.merged_ids = {"CF-9"}
    page = await bench.service.page("")
    assert [(h.id, h.retired) for h in page.retired] == [
        ("2026-10-01-ends", "ended when CF-9 merged")
    ]


async def test_a_retired_entry_is_history_with_its_reason_and_where_it_went(bench: Bench) -> None:
    await bench.seed(
        "2026-10-01-old", "Old", retired='merged into "New"', merged_into="2026-10-02-new"
    )
    await bench.seed("2026-10-02-new", "New")
    page = await bench.service.page("")
    assert [(h.id, h.retired, h.merged_into, h.repository) for h in page.retired] == [
        ("2026-10-01-old", 'merged into "New"', "2026-10-02-new", "sample")
    ]


async def test_a_superseded_entry_is_not_loaded_and_names_what_superseded_it(bench: Bench) -> None:
    await bench.seed("2026-10-01-old", "Merge at once")
    await bench.seed("2026-10-02-new", "Land through one queue", supersedes=["2026-10-01-old"])
    page = await bench.service.page("")
    by_id = {r.id: r for r in page.unreviewed}
    assert (by_id["2026-10-01-old"].loaded, by_id["2026-10-01-old"].superseded_by) == (
        False, "2026-10-02-new",
    )  # fmt: skip
    assert by_id["2026-10-02-new"].supersedes == "2026-10-01-old"
    assert by_id["2026-10-02-new"].loaded


async def test_a_proposal_a_retired_entry_and_an_enforced_lesson_are_not_loaded(
    bench: Bench,
) -> None:
    bench.git.files = {"tests/test_a.py": "def test_guarded():\n    pass\n"}
    await bench.seed("2026-10-01-p", "Proposed", proposed=True)
    await bench.seed(
        "2026-10-01-g", "Guarded", kind="lesson", guard="test_guarded", reviewed="2026-11-01"
    )
    page = await bench.service.page("")
    by_id = {r.id: r for r in page.unreviewed + page.lessons}
    assert (by_id["2026-10-01-p"].loaded, by_id["2026-10-01-p"].proposed) == (False, True)
    assert (by_id["2026-10-01-g"].loaded, by_id["2026-10-01-g"].guard_state) == (False, "enforced")


async def test_an_entry_citing_a_deleted_path_is_stale_cites_and_in_the_queue(
    bench: Bench, tmp_path: Path
) -> None:
    (tmp_path / "sample" / "src").mkdir(parents=True)
    (tmp_path / "sample" / "src" / "kept.py").write_text("x", encoding="utf-8")
    bench.git.files = {"tests/test_a.py": "def test_present():\n    pass\n"}
    await bench.seed(
        "2026-11-01-cites", "Cites things", reviewed="2026-11-01",
        cites=["src/kept.py", "src/removed.py", "test_present", "test_removed"],
    )  # fmt: skip
    await bench.seed("2026-11-01-fine", "Fine", reviewed="2026-11-01", cites=["src/kept.py"])
    page = await bench.service.page("")
    cited = next(r for r in page.rules if r.id == "2026-11-01-cites")
    assert cited.stale_cites == ["src/removed.py", "test_removed"]
    assert cited.cites == "src/kept.py, src/removed.py, test_present, test_removed"
    assert [r.id for r in page.review_queue] == ["2026-11-01-cites"]


async def test_an_entry_overdue_for_review_is_queued_after_its_due_day_only(bench: Bench) -> None:
    await bench.seed("2026-08-11-due-yesterday", "Due yesterday", reviewed="2026-08-11")
    await bench.seed("2026-08-12-due-today", "Due today", reviewed="2026-08-12")
    await bench.seed("2026-08-01-proposed", "Proposed", proposed=True)
    await bench.service.deliver("run-1", "CF-1", "sample", TicketContext(), now=NOW)
    page = await bench.service.page("")
    assert [r.id for r in page.review_queue] == ["2026-08-11-due-yesterday"]


async def test_the_queue_is_ordered_by_due_day_then_id_across_repositories(bench: Bench) -> None:
    await bench.seed("2026-01-02-b", "B", reviewed="2026-01-02")
    await bench.seed("2026-01-01-a", "A", reviewed="2026-01-01", repository="second")
    await bench.seed("2026-01-02-a", "A too", reviewed="2026-01-02")
    for repository in ("sample", "second"):
        await bench.service.deliver("run-1", "CF-1", repository, TicketContext(), now=NOW)
    page = await bench.service.page("")
    assert [r.id for r in page.review_queue] == ["2026-01-01-a", "2026-01-02-a", "2026-01-02-b"]


async def test_an_entry_unused_for_more_than_30_days_is_unused_and_queued(bench: Bench) -> None:
    await bench.seed("2026-10-10-idle", "Idle", reviewed="2026-11-09")
    await bench.seed("2026-10-11-fresh", "Fresh", reviewed="2026-11-09")
    page = await bench.service.page("")
    assert {r.id: r.unused for r in page.rules} == {
        "2026-10-10-idle": True,
        "2026-10-11-fresh": False,
    }
    assert [r.id for r in page.review_queue] == ["2026-10-10-idle"]


async def test_a_receipt_resets_the_count_of_unused_days(bench: Bench) -> None:
    await bench.seed("2026-01-01-old", "Old", reviewed="2026-11-09")
    await bench.service.deliver(
        "run-1", "CF-1", "sample", TicketContext(), now=NOW - timedelta(days=30)
    )
    assert not (await bench.service.page("")).rules[0].unused
    await bench.service.deliver(
        "run-2", "CF-2", "sample", TicketContext(), now=NOW - timedelta(days=1)
    )
    assert not (await bench.service.page("")).rules[0].unused


async def test_a_last_receipt_31_days_ago_leaves_the_entry_unused(bench: Bench) -> None:
    await bench.seed("2026-01-01-old", "Old", reviewed="2026-11-09")
    await bench.service.deliver(
        "run-1", "CF-1", "sample", TicketContext(), now=NOW - timedelta(days=31)
    )
    page = await bench.service.page("")
    assert (page.rules[0].unused, page.rules[0].last_received) == (True, "2026-10-10")


async def test_an_archived_a_proposed_and_a_superseded_entry_are_never_unused(bench: Bench) -> None:
    await bench.seed("2026-01-01-archived", "Archived", scope="archive", reviewed="2026-11-09")
    await bench.seed("2026-01-01-proposed", "Proposed", proposed=True, reviewed="2026-11-09")
    await bench.seed("2026-01-01-old", "Old", reviewed="2026-11-09")
    await bench.seed("2026-02-01-new", "New", supersedes=["2026-01-01-old"], reviewed="2026-11-09")
    page = await bench.service.page("")
    unused = {r.id: r.unused for r in [*page.rules, *page.unreviewed]}
    assert unused == {
        "2026-01-01-archived": False,
        "2026-01-01-proposed": False,
        "2026-01-01-old": False,
        "2026-02-01-new": True,
    }


async def test_received_by_lists_the_runs_oldest_first_with_a_count_and_the_last_day(
    bench: Bench,
) -> None:
    await bench.seed("2026-11-01-a", "A rule", reviewed="2026-11-09")
    await bench.service.deliver(
        "run-2", "CF-2", "sample", TicketContext(), now=NOW - timedelta(days=1)
    )
    await bench.service.deliver(
        "run-1", "CF-1", "sample", TicketContext(), now=NOW - timedelta(days=3)
    )
    page = await bench.service.page("")
    record = page.rules[0]
    assert [(r.run, r.ticket_id) for r in record.received_by] == [
        ("run-1", "CF-1"),
        ("run-2", "CF-2"),
    ]
    assert (record.received_count, record.last_received, record.unused) == (2, "2026-11-09", False)


async def test_the_budget_leaves_out_lessons_past_it_and_reports_the_overflow(bench: Bench) -> None:
    for day, size in (
        ("2026-11-02", 2001),
        ("2026-11-03", 2000),
        ("2026-11-04", 2000),
        ("2026-11-05", 2000),
    ):
        await bench.seed(f"{day}-lesson", "x" * (size - 3), kind="lesson", reviewed="2026-11-09")
    page = await bench.service.page("")
    assert [(x.repository, x.id) for x in page.left_out] == [("sample", "2026-11-02-lesson")]
    assert {r.id: (r.left_out, r.loaded) for r in page.lessons}["2026-11-02-lesson"] == (
        True,
        False,
    )
    assert page.loaded_chars == 8001
    assert page.rules_over == 0


async def test_rules_past_the_budget_are_all_loaded_and_the_overflow_is_reported(
    bench: Bench,
) -> None:
    for day in ("2026-11-02", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07"):
        await bench.seed(f"{day}-rule", "x" * 1997, reviewed="2026-11-09")
    page = await bench.service.page("")
    assert page.rules_over == 2000
    assert page.left_out == []
    assert all(r.loaded for r in page.rules)


async def test_a_pair_and_a_proposal_come_with_their_statements_and_repository(
    bench: Bench,
) -> None:
    await bench.seed(
        "2026-10-01-squash",
        "Squash ticket branches before landing them through the merge queue",
        reviewed="2026-11-09",
    )
    await bench.seed(
        "2026-10-05-queue",
        "Never let the merge queue take ticket branches unsquashed",
        reviewed="2026-11-09",
    )
    await bench.seed(
        "2026-09-01-run-the-gate",
        "Run the gate before every push of a ticket branch",
        reviewed="2026-11-09",
    )
    await bench.seed(
        "2026-09-05-run-the-gate-each",
        "Run the gate before each push of the ticket branch",
        reviewed="2026-11-09",
    )
    page = await bench.service.page("")
    assert [p.model_dump() for p in page.pairs] == [
        {
            "repository": "sample", "one": "2026-10-01-squash", "other": "2026-10-05-queue",
            "one_statement": "Squash ticket branches before landing them through the merge queue",
            "other_statement": "Never let the merge queue take ticket branches unsquashed",
            "terms": ["branches", "merge", "queue", "ticket"], "contradicts": True,
        }
    ]  # fmt: skip
    assert [p.model_dump() for p in page.proposals] == [
        {
            "repository": "sample", "action": "merge",
            "statement": "Run the gate before each push of the ticket branch",
            "into_statement": "Run the gate before every push of a ticket branch",
            "id": "2026-09-05-run-the-gate-each", "into": "2026-09-01-run-the-gate",
        }
    ]  # fmt: skip


async def test_the_retire_proposal_names_the_guard_and_its_reason(bench: Bench) -> None:
    bench.git.files = {
        "tests/test_g.py": "def guarded_test():\n    pass\n\n\ndef test_x():\n    pass\n"
    }
    bench.git.files["tests/test_g.py"] = "def test_guarded():\n    pass\n"
    await bench.seed(
        "2026-08-12-close-the-ledger",
        "Close the ledger handle after reading it",
        kind="lesson",
        guard="test_guarded",
    )
    page = await bench.service.page("")
    assert [p.model_dump() for p in page.proposals] == [
        {
            "repository": "sample", "action": "retire",
            "statement": "Close the ledger handle after reading it",
            "reason": "its guard test_guarded is a test now",
            "id": "2026-08-12-close-the-ledger", "guard": "test_guarded",
        }
    ]  # fmt: skip


async def test_pairs_proposals_and_the_queue_are_read_per_repository(bench: Bench) -> None:
    await bench.seed("2026-01-01-old", "Old", reviewed="2026-01-01")
    await bench.seed("2026-01-01-other", "Other", reviewed="2026-01-01", repository="second")
    assert [r.id for r in await bench.service.review_queue("sample")] == ["2026-01-01-old"]
    assert [r.id for r in await bench.service.review_queue("second")] == ["2026-01-01-other"]
    assert await bench.service.pairs("sample") == []
    assert await bench.service.proposals("sample") == []


async def test_the_page_reads_test_names_only_when_an_entry_needs_them(bench: Bench) -> None:
    await bench.seed("2026-10-01-plain", "Plain")
    await bench.service.page("")
    assert bench.git.calls.get("tracked_files") is None
    await bench.seed("2026-10-01-guarded", "Guarded", kind="lesson", guard="test_x")
    await bench.service.page("")
    assert bench.git.calls["tracked_files"] == 1


async def test_a_repository_that_is_not_tracked_is_unknown_to_the_rules(bench: Bench) -> None:
    with pytest.raises(NotFoundError, match=r"unknown repository"):
        await bench.service.rules_for("nowhere", TicketContext())
