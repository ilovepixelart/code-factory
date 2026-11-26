"""The checks every entry meets on its way in, run by the base add and propose."""

from pathlib import Path

import pytest

from code_factory.memory.models import NewMemory
from code_factory.memory.repository import MemoryRepository
from code_factory.memory_extras.adapters import DefinedTests, RepositoryFiles
from code_factory.platform.errors import BadRequestError, ConflictError
from memory_extras_bench import Bench
from memory_extras_values import OWNER

REPO = "sample"
CLAUDE = (
    "# Rules\n\n- Commits and pull requests carry no AI attribution of any kind.\n"
    "- Build it, run the tests the change reaches\n  and commit.\n"
)
PAIRED = "2026-10-01-squash-first"


def draft(statement: str, kind: str = "rule", **fields: object) -> NewMemory:
    return NewMemory(repository=REPO, kind=kind, statement=statement, source="chat", **fields)  # ty: ignore[invalid-argument-type]


async def ids(bench: Bench) -> list[str]:
    return [e.id for e in await bench.memory.list_entries(REPO, include_retired=True)]


async def test_a_statement_restating_a_claude_md_line_is_refused_naming_the_line(
    bench: Bench,
) -> None:
    bench.git.files = {"CLAUDE.md": CLAUDE}
    given = draft("Commits and pull requests carry no AI attribution of any kind")
    with pytest.raises(
        BadRequestError,
        match=r"^restates CLAUDE.md line 3: Commits and pull requests carry no AI attribution",
    ):
        await bench.memory.add(given, by=OWNER)
    assert await ids(bench) == []


async def test_a_statement_that_only_shares_words_with_claude_md_is_admitted(bench: Bench) -> None:
    bench.git.files = {"CLAUDE.md": CLAUDE}
    await bench.memory.add(draft("Run the tests before you commit anything"), by=OWNER)
    assert len(await ids(bench)) == 1


async def test_a_repository_without_a_claude_md_restates_nothing(bench: Bench) -> None:
    await bench.memory.add(draft("Commits carry no attribution of any kind at all"), by=OWNER)
    assert len(await ids(bench)) == 1


async def test_a_proposal_meets_the_same_restatement_check(bench: Bench) -> None:
    bench.git.files = {"CLAUDE.md": CLAUDE}
    given = draft("Build it, run the tests the change reaches and commit")
    with pytest.raises(BadRequestError, match=r"restates CLAUDE.md line 4"):
        await bench.memory.propose(given, by="run-1")


BUDGET_SENTENCE = (
    r"^the rules and decisions every session loads would take 2000 characters over the memory "
    r"budget of 8,000: merge, scope or retire one before adding another$"
)


async def fill(bench: Bench, count: int) -> None:
    for number in range(count):
        await bench.seed(f"2026-11-0{number + 1}-rule", "x" * 1997)


async def test_a_rule_loading_everywhere_that_passes_the_budget_is_refused_with_the_sentence(
    bench: Bench,
) -> None:
    await fill(bench, 4)
    given = draft("y" * 1997)
    with pytest.raises(BadRequestError, match=BUDGET_SENTENCE):
        await bench.memory.add(given, by=OWNER)
    assert len(await ids(bench)) == 4


async def test_a_rule_that_fits_the_budget_exactly_is_admitted(bench: Bench) -> None:
    await fill(bench, 3)
    await bench.memory.add(draft("y" * 1997), by=OWNER)
    assert len(await ids(bench)) == 4


async def test_a_rule_that_supersedes_one_is_judged_without_the_entry_it_retires(
    bench: Bench,
) -> None:
    await fill(bench, 4)
    await bench.memory.add(draft("y" * 1997, supersedes=["2026-11-01-rule"]), by=OWNER)
    entries = await bench.memory.list_entries(REPO, include_retired=True)
    assert [e.id for e in entries if e.retired] == ["2026-11-01-rule"]
    assert len(entries) == 5


async def test_a_proposal_retires_nothing_so_it_is_judged_with_every_entry(bench: Bench) -> None:
    await fill(bench, 4)
    given = draft("y" * 1997, supersedes=["2026-11-01-rule"])
    with pytest.raises(BadRequestError, match=BUDGET_SENTENCE):
        await bench.memory.propose(given, by="run-1")


async def test_a_lesson_a_scoped_rule_and_a_decision_are_judged_apart_for_the_budget(
    bench: Bench,
) -> None:
    await fill(bench, 4)
    await bench.memory.add(draft("y" * 1997, kind="lesson"), by=OWNER)
    await bench.memory.add(draft("z" * 1997, scope="build"), by=OWNER)
    given = draft("w" * 1997, kind="decision")
    with pytest.raises(BadRequestError, match=r"memory budget of 8,000"):
        await bench.memory.add(given, by=OWNER)


async def test_a_core_lesson_is_never_refused_for_the_budget_though_it_loads_first(
    bench: Bench,
) -> None:
    await fill(bench, 4)
    await bench.memory.add(draft("y" * 1997, kind="lesson", scope="core"), by=OWNER)
    assert len(await ids(bench)) == 5


async def test_a_superseded_id_that_is_no_entry_is_refused(bench: Bench) -> None:
    given = draft("Land through one queue", supersedes=["2026-01-01-nothing"])
    with pytest.raises(BadRequestError, match=r"^no entry 2026-01-01-nothing to supersede$"):
        await bench.memory.add(given, by=OWNER)


async def test_a_retired_id_may_be_named_as_superseded(bench: Bench) -> None:
    await bench.seed("2026-09-01-old", "Old", retired="done")
    await bench.memory.add(draft("Land through one queue", supersedes=["2026-09-01-old"]), by=OWNER)
    assert len(await ids(bench)) == 2


async def test_a_bad_scope_or_expiry_is_refused_by_the_field_check(bench: Bench) -> None:
    given = draft("Scoped", scope="bulid")
    with pytest.raises(BadRequestError, match=r"^scope names core"):
        await bench.memory.add(given, by=OWNER)
    given = draft("Ends", expires="soon")
    with pytest.raises(BadRequestError, match=r"^expires is a date, YYYY-MM-DD$"):
        await bench.memory.add(given, by=OWNER)


async def test_the_fields_are_checked_before_the_restatement_and_the_restatement_before_the_budget(
    bench: Bench,
) -> None:
    bench.git.files = {"CLAUDE.md": CLAUDE}
    await fill(bench, 4)
    restating = "Commits and pull requests carry no AI attribution of any kind"
    given = draft(restating, scope="bulid")
    with pytest.raises(BadRequestError, match=r"^scope names core"):
        await bench.memory.add(given, by=OWNER)
    given = draft(restating + "!" + "y" * 1900)
    with pytest.raises(BadRequestError, match=r"^restates CLAUDE.md"):
        await bench.memory.add(given, by=OWNER)


async def test_the_budget_is_checked_before_the_superseded_ids(bench: Bench) -> None:
    await fill(bench, 4)
    given = draft("y" * 1997, supersedes=["2026-01-01-nothing"])
    with pytest.raises(BadRequestError, match=r"memory budget"):
        await bench.memory.add(given, by=OWNER)


async def paired(bench: Bench) -> None:
    await bench.seed(PAIRED, "Always rebase ticket branches onto main before landing")


async def test_an_entry_on_the_subject_of_an_active_one_is_refused_until_answered(
    bench: Bench,
) -> None:
    await paired(bench)
    given = draft("Never rebase ticket branches onto main")
    with pytest.raises(
        ConflictError,
        match=rf"^it is on the subject of {PAIRED}: pass --supersedes {PAIRED} or --keep-both$",
    ):
        await bench.memory.add(given, by=OWNER, check_pairs=True)
    assert await ids(bench) == [PAIRED]


async def test_keep_both_files_the_entry_beside_the_one_it_is_paired_with(bench: Bench) -> None:
    await paired(bench)
    await bench.memory.add(
        draft("Never rebase ticket branches onto main"), by=OWNER, check_pairs=True, keep_both=True
    )
    assert len(await ids(bench)) == 2


async def test_superseding_the_paired_entry_answers_the_question(bench: Bench) -> None:
    await paired(bench)
    await bench.memory.add(
        draft("Never rebase ticket branches onto main", supersedes=[PAIRED]),
        by=OWNER,
        check_pairs=True,
    )
    assert len(await ids(bench)) == 2


async def test_the_pair_is_not_checked_when_the_caller_does_not_ask(bench: Bench) -> None:
    await paired(bench)
    await bench.memory.add(draft("Never rebase ticket branches onto main"), by=OWNER)
    assert len(await ids(bench)) == 2


async def test_a_retired_or_ended_entry_is_no_subject_to_be_paired_with(bench: Bench) -> None:
    await bench.seed(
        "2026-10-01-retired",
        "Always rebase ticket branches onto main before landing",
        retired="done",
    )
    await bench.seed(
        "2026-10-02-ended",
        "Always rebase ticket branches onto main before landing",
        expires="2026-11-01",
    )
    await bench.memory.add(
        draft("Never rebase ticket branches onto main"), by=OWNER, check_pairs=True
    )
    assert len(await ids(bench)) == 3


async def test_an_entry_the_consolidation_would_merge_away_is_not_a_pair(bench: Bench) -> None:
    await bench.seed("2026-09-01-gate", "Run the gate before every push of a ticket branch")
    await bench.memory.add(
        draft("Run the gate before each push of the ticket branch"), by=OWNER, check_pairs=True
    )
    assert len(await ids(bench)) == 2


async def test_a_new_ticket_asks_about_the_open_tickets_it_looks_like(bench: Bench) -> None:
    bench.tickets.titles["sample"] = [
        ("CF-1", "Production errors and alerts do not become tickets"),
        ("CF-5", "Production errors become very long tickets in lists"),
    ]
    asked = await bench.service.duplicate_questions(
        "sample", "Production errors do not become bug tickets"
    )
    assert [q.ticket_id for q in asked] == ["CF-1"]
    assert bench.service.alike("Alpha beta gamma delta", "Alpha beta gamma epsilon")
    assert await bench.service.duplicate_questions("sample", "Column scrollbars keep padding") == []


async def test_an_entry_of_an_untracked_repository_is_admitted_without_reading_its_files(
    bench: Bench,
) -> None:
    bench.git.files = {"CLAUDE.md": CLAUDE}
    stray = NewMemory(
        repository="untracked",
        kind="lesson",
        statement="Commits and pull requests carry no AI attribution of any kind",
        source="chat",
        guard="test_x",
    )
    await bench.memory.add(stray, by=OWNER, check_pairs=True)
    assert len(await bench.memory.list_entries("untracked")) == 1
    assert bench.git.calls.get("read_text_below") is None


async def test_files_and_tests_are_read_before_the_repository_additions_are_locked(
    bench: Bench, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    lock = MemoryRepository.lock_additions
    claude = RepositoryFiles.claude_md
    defined = DefinedTests.defined

    async def locking(self: MemoryRepository, repository: str) -> None:
        events.append("lock")
        await lock(self, repository)

    async def reading(self: RepositoryFiles, root: Path) -> str:
        events.append("claude_md")
        return await claude(self, root)

    async def scanning(self: DefinedTests, repository: str, root: Path) -> frozenset[str]:
        events.append("defined")
        return await defined(self, repository, root)

    monkeypatch.setattr(MemoryRepository, "lock_additions", locking)
    monkeypatch.setattr(RepositoryFiles, "claude_md", reading)
    monkeypatch.setattr(DefinedTests, "defined", scanning)
    await bench.seed("2026-10-01-guarded", "Guarded rule", guard="test_x")
    await bench.memory.add(draft("Keep migrations small and reversible"), by=OWNER)
    assert events == ["claude_md", "defined", "lock"]
