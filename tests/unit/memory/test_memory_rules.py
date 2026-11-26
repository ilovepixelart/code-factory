"""The pure memory rules, with expected values from the previous implementation's memory format
and its API golden (an entry `2026-10-01-keep-it-small` written on 2026-10-01 is due for review
on 2026-12-30)."""

from datetime import date

import pytest

from code_factory.memory.models import MemoryEntry, MemoryFields
from code_factory.memory.rules import (
    check_entry,
    check_new,
    entry_name,
    is_incomplete,
    is_stale,
    matches,
    recall,
    review_due,
    slug,
)
from code_factory.platform.errors import BadRequestError


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("Keep it small and test first", "keep-it-small-and-test-first"),
        ("The gate ran twice on one tree!", "the-gate-ran-twice-on-one-tree"),
        ("One two three four five six seven eight nine", "one-two-three-four-five-six-seven-eight"),
        ("Don't use CF-12's branch", "don-t-use-cf-12-s-branch"),
        ("!!!", "record"),
    ],
)
def test_a_name_is_the_first_eight_words_in_lower_case_joined_by_hyphens(
    words: str, expected: str
) -> None:
    assert slug(words) == expected


def test_a_taken_name_is_numbered_from_two() -> None:
    day = date(2026, 10, 1)
    assert entry_name(day, "Ship small", set()) == "2026-10-01-ship-small"
    assert entry_name(day, "Ship small", {"2026-10-01-ship-small"}) == "2026-10-01-ship-small-2"
    taken = {"2026-10-01-ship-small", "2026-10-01-ship-small-2"}
    assert entry_name(day, "Ship small", taken) == "2026-10-01-ship-small-3"


@pytest.mark.parametrize(
    ("statement", "fields", "problem"),
    [
        (" ", MemoryFields(source="s"), "an entry needs a statement"),
        ("Do it", MemoryFields(source="s", why="one\ntwo"), "are one line each"),
        ("Do it", MemoryFields(source="s", expires="31.12.2026"), "expires is a date"),
        ("Do it", MemoryFields(source="s", until="CF-1 CF-2"), "until names one ticket id"),
        ("Do it", MemoryFields(source="s", scope="core, nowhere"), "scope names core, archive"),
        ("Do it", MemoryFields(source="s", scope="archive, core"), "archive is a scope of its own"),
        ("Do it", MemoryFields(source=" "), "an entry needs a source"),
    ],
)
def test_an_entry_that_cannot_be_written_is_refused_with_why(
    statement: str, fields: MemoryFields, problem: str
) -> None:
    with pytest.raises(BadRequestError, match=problem):
        check_new(statement, fields)


@pytest.mark.parametrize(
    "scope", ["", "core", "spec, build", "review", "label:ui", "src/**/*.py", "archive"]
)
def test_an_entry_with_known_scope_terms_is_taken(scope: str) -> None:
    check_new("Do it", MemoryFields(source="chat", scope=scope, expires="2026-12-31", until="CF-9"))


def test_an_older_entry_without_a_source_still_passes_the_edit_check() -> None:
    check_entry("Do it", MemoryFields())


def test_review_falls_due_ninety_days_after_the_last_review_or_the_writing() -> None:
    assert review_due(date(2026, 10, 1), "") == "2026-12-30"
    assert review_due(date(2026, 10, 1), "2026-11-01") == "2027-01-30"


def test_an_entry_is_stale_after_thirty_days_without_review() -> None:
    written = date(2026, 10, 1)
    assert not is_stale(written, "", date(2026, 10, 31))
    assert is_stale(written, "", date(2026, 11, 1))
    assert not is_stale(written, "2026-10-20", date(2026, 11, 1))


def test_an_entry_without_its_why_or_source_is_incomplete() -> None:
    assert is_incomplete("Keep it small", "", "conversation")
    assert is_incomplete("Keep it small", "Big changes hide bugs", "")
    assert not is_incomplete("Keep it small", "Big changes hide bugs", "conversation")


@pytest.mark.parametrize(
    ("query", "found"),
    [("keep small", True), ("KEEP", True), ("keep gate", False), ("nothing matches this", False)],
)
def test_a_search_needs_every_word_in_the_name_statement_or_why(query: str, found: bool) -> None:
    assert matches(query, "2026-10-01-keep-it-small", "Keep it small and test first", "") is found


def entry(name: str, kind: str, statement: str, **fields: object) -> MemoryEntry:
    return MemoryEntry.model_validate(
        {
            "repository": "sample",
            "id": name,
            "kind": kind,
            "statement": statement,
            "date": "2026-10-01",
            "reviewed": "",
            "proposed": False,
            "verdict": "",
            "retired": "",
            "merged_into": "",
            "status": "active",
            "review_due": "2026-12-30",
            "stale": False,
            "incomplete": False,
            **fields,
        }
    )


def test_recall_gives_core_entries_then_rules_and_decisions_then_lessons_newest_first() -> None:
    entries = [
        entry("a", "lesson", "Run the gate once", why="It ran twice"),
        entry("b", "decision", "Ship small pull requests", date="2026-09-15"),
        entry("c", "rule", "Old rule", date="2026-09-01"),
        entry("d", "rule", "New rule", date="2026-10-02"),
        entry("e", "decision", "Spell it out", scope="core"),
        entry("f", "rule", "Only for review", scope="review"),
        entry("g", "rule", "Waiting for approval", proposed=True, status="proposed"),
        entry("h", "rule", "Kept in the index", scope="archive"),
        entry("i", "rule", "Ended", expires="2026-11-01"),
        entry("j", "rule", "Build only", scope="build"),
    ]
    assert recall(entries, "build", date(2026, 11, 23)) == (
        "- Spell it out\n"
        "- New rule\n"
        "- Build only\n"
        "- Ship small pull requests\n"
        "- Old rule\n"
        "- Run the gate once Why: It ran twice\n"
    )
