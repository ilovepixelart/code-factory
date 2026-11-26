"""The order sessions load entries in, the budget that cuts it, and the recall line."""

from code_factory.memory.models import MemoryEntry
from code_factory.memory_extras.rules import (
    overflow,
    recall_line,
    recall_size,
    title,
    within_budget,
)
from memory_extras_values import entry


def make(id_: str, kind: str, scope: str, statement: str) -> MemoryEntry:
    return entry(id_, statement, kind=kind, scope=scope)


def ids(entries: list[MemoryEntry]) -> list[str]:
    return [e.id for e in entries]


def test_entries_load_core_then_rules_then_lessons_newest_first() -> None:
    entries = [
        make("2026-10-01-old-lesson", "lesson", "", "Old lesson"),
        make("2026-11-01-new-lesson", "lesson", "", "New lesson"),
        make("2026-10-01-old-rule", "rule", "", "Old rule"),
        make("2026-11-02-new-decision", "decision", "", "New decision"),
        make("2026-11-05-a-rule", "rule", "", "A rule"),
        make("2026-11-05-b-rule", "rule", "", "B rule"),
        make("2026-09-01-core-lesson", "lesson", "core", "Core lesson"),
    ]
    kept, left = within_budget(entries)
    assert ids(kept) == [
        "2026-09-01-core-lesson",
        "2026-11-05-b-rule",
        "2026-11-05-a-rule",
        "2026-11-02-new-decision",
        "2026-10-01-old-rule",
        "2026-11-01-new-lesson",
        "2026-10-01-old-lesson",
    ]
    assert left == []


def sized(day: str, size: int) -> MemoryEntry:
    """A lesson whose recall line, `- ` and its statement, takes `size` characters with its end."""
    return make(f"{day}-rule", "lesson", "", "x" * (size - 3))


def test_lessons_past_the_budget_are_left_out_in_load_order() -> None:
    over = [
        sized("2026-11-02", 2001),
        sized("2026-11-03", 2000),
        sized("2026-11-04", 2000),
        sized("2026-11-05", 2000),
        sized("2026-11-01", 4),
    ]
    kept, left = within_budget(over)
    assert ids(kept) == ["2026-11-05-rule", "2026-11-04-rule", "2026-11-03-rule"]
    assert ids(left) == ["2026-11-02-rule", "2026-11-01-rule"]


def test_lessons_filling_the_budget_exactly_are_all_kept() -> None:
    exact = [sized(f"2026-11-0{n}", 2000) for n in (2, 3, 4, 5)]
    kept, left = within_budget(exact)
    assert len(kept) == 4
    assert left == []


def test_rules_and_decisions_past_the_budget_are_all_kept_and_the_overflow_is_reported() -> None:
    rule = lambda day: make(f"{day}-rule", "rule", "", "x" * 1997)  # noqa: E731
    entries = [
        rule("2026-11-02"),
        make("2026-11-03-decision", "decision", "", "y" * 1997),
        rule("2026-11-04"),
        rule("2026-11-05"),
        rule("2026-11-06"),
        make("2026-11-09-tiny-lesson", "lesson", "", "Tiny"),
    ]
    kept, left = within_budget(entries)
    assert len(kept) == 5
    assert ids(left) == ["2026-11-09-tiny-lesson"]
    assert overflow(entries) == 2000
    assert overflow(entries[:4]) == 0


def test_a_marked_line_counts_its_mark_against_the_budget() -> None:
    lesson = lambda day, size: make(f"{day}-lesson", "lesson", "", "z" * size)  # noqa: E731
    entries = [lesson("2026-11-02", 3996), lesson("2026-11-01", 3996)]
    mark = lambda e: 10 if e.id.startswith("2026-11-02") else 0  # noqa: E731
    kept, left = within_budget(entries, mark)
    plain_kept, _ = within_budget(entries)
    assert len(plain_kept) == 2
    assert ids(kept) == ["2026-11-02-lesson"]
    assert ids(left) == ["2026-11-01-lesson"]


def test_a_marked_rule_counts_its_mark_in_the_overflow() -> None:
    rules = [make("2026-11-02-rule", "rule", "", "x" * 7988)]
    assert overflow(rules, lambda _: 20) == 11
    assert overflow(rules) == 0


def test_the_recall_line_is_the_statement_then_its_why() -> None:
    assert recall_line(entry(statement="Ship small")) == "- Ship small"
    assert (
        recall_line(entry(statement="Ship small", why="It lands")) == "- Ship small Why: It lands"
    )
    assert recall_size(entry(statement="Ship small")) == len("- Ship small") + 1
    assert recall_size(entry(statement="Ship small"), 5) == len("- Ship small") + 6


def test_a_title_is_the_statement_cut_to_sixty_characters() -> None:
    assert title("- " + "a" * 70 + " Why: because") == "a" * 60
    assert title("- Ship small Why: it lands") == "Ship small"
