"""Entries on one subject, the consolidation that merges or retires, and title similarity."""

from datetime import UTC, datetime

import pytest

from code_factory.memory.models import MemoryEntry
from code_factory.memory_extras.models import Merge, Pair, Retire
from code_factory.memory_extras.rules import (
    alike,
    duplicate_questions,
    pairs,
    proposals,
    retire_reason,
)
from code_factory.platform.text import epoch_day
from memory_extras_values import entry

NOW = epoch_day(datetime(2026, 11, 10, tzinfo=UTC))
SQUASH = "2026-10-01-squash"
QUEUE = "2026-10-05-queue"
SMALL = "2026-10-03-small"


def many(*statements: tuple[str, str]) -> list[MemoryEntry]:
    return [entry(id_, statement) for id_, statement in statements]


def test_two_entries_sharing_distinctive_words_are_a_pair_for_the_owner_to_read_together() -> None:
    found = pairs(
        many(
            (SQUASH, "Squash ticket branches before landing them through the merge queue"),
            (QUEUE, "The merge queue takes ticket branches as they are"),
            (SMALL, "Keep pull requests small"),
        ),
        frozenset(),
        NOW,
    )
    assert found == [
        Pair(
            one=SQUASH,
            other=QUEUE,
            terms=("branches", "merge", "queue", "ticket"),
            contradicts=False,
        )
    ]


def test_a_negation_on_the_shared_subject_marks_the_pair_as_a_possible_contradiction() -> None:
    found = pairs(
        many(
            (SQUASH, "Squash ticket branches before landing them through the merge queue"),
            (QUEUE, "Never let the merge queue take ticket branches unsquashed"),
        ),
        frozenset(),
        NOW,
    )
    assert [(p.terms, p.contradicts) for p in found] == [
        (("branches", "merge", "queue", "ticket"), True)
    ]


@pytest.mark.parametrize("apostrophe", ["'", "\N{RIGHT SINGLE QUOTATION MARK}"])
def test_a_dont_on_the_shared_subject_is_a_negation(apostrophe: str) -> None:
    found = pairs(
        many(
            (SQUASH, "Squash ticket branches before landing them through the merge queue"),
            (QUEUE, f"Don{apostrophe}t let the merge queue take ticket branches unsquashed"),
        ),
        frozenset(),
        NOW,
    )
    assert [(p.terms, p.contradicts) for p in found] == [
        (("branches", "merge", "queue", "ticket"), True)
    ]


def test_two_negated_clauses_on_one_subject_agree_and_do_not_contradict() -> None:
    found = pairs(
        many(
            (SQUASH, "Never push ticket branches to the merge queue"),
            (QUEUE, "Do not let the merge queue take ticket branches"),
        ),
        frozenset(),
        NOW,
    )
    assert [(p.terms, p.contradicts) for p in found] == [
        (("branches", "merge", "queue", "ticket"), False)
    ]


def test_always_against_never_on_one_subject_contradicts() -> None:
    found = pairs(
        many(
            (SQUASH, "Always rebase ticket branches onto main before landing"),
            (QUEUE, "Never rebase ticket branches onto main"),
        ),
        frozenset(),
        NOW,
    )
    assert [(p.terms, p.contradicts) for p in found] == [
        (("branches", "main", "onto", "rebase", "ticket"), True)
    ]


def test_opposing_clauses_inside_longer_statements_contradict() -> None:
    found = pairs(
        many(
            (SQUASH, "Keep pull requests small; squash ticket branches before landing them."),
            (
                QUEUE,
                "Write the reason in the ticket; never squash ticket branches before landing them.",
            ),
        ),
        frozenset(),
        NOW,
    )
    assert [(p.terms, p.contradicts) for p in found] == [
        (("branches", "landing", "squash", "ticket"), True)
    ]


def test_a_negation_in_a_clause_about_something_else_is_not_a_contradiction() -> None:
    agents = (
        "2026-10-07-agent-definitions",
        (
            "Agent definitions live in the state folder, per machine; provider keys as the "
            "2026-10-29 secrets rule says (CF-793); connections first through the Anthropic "
            "protocol of the runtime the board already drives; a team works by roles per column "
            "on different tickets in parallel, with a reviewer that did not write the code; local "
            "models are capped by tokens and run time."
        ),
    )
    ask = (
        "2026-10-07-ask-the-owner",
        (
            "Ask the owner only choices that change what ships: product behaviour, a visible UI "
            "change, a process rule; decide what the docs, the code or a measurement already "
            "settle, and write the reason in the ticket."
        ),
    )
    found = pairs(many(agents, ask), frozenset(), NOW)
    assert [(p.terms, p.contradicts) for p in found] == [
        (("already", "code", "rule", "write"), False)
    ]


def test_a_word_held_by_more_than_four_active_entries_names_no_subject() -> None:
    same = [
        (f"2026-10-0{n}-e{n}", f"Alpha beta gamma delta unique{n}x words{n}") for n in range(1, 5)
    ]
    assert len(pairs(many(*same), frozenset(), NOW)) == 6
    five = [*same, ("2026-10-09-e9", "Alpha beta gamma delta unique9x words9")]
    assert pairs(many(*five), frozenset(), NOW) == []


def test_a_retired_entry_is_in_no_pair() -> None:
    entries = [
        entry(SQUASH, "Squash ticket branches before landing them through the merge queue"),
        entry(QUEUE, "The merge queue takes ticket branches as they are", retired="done"),
    ]
    assert pairs(entries, frozenset(), NOW) == []


def test_an_entry_a_consolidation_would_merge_away_is_in_no_pair() -> None:
    entries = many(
        ("2026-09-01-run-the-gate", "Run the gate before every push of a ticket branch"),
        ("2026-09-05-run-the-gate-each", "Run the gate before each push of the ticket branch"),
    )
    assert proposals(entries, frozenset(), NOW) == [
        Merge(from_id="2026-09-05-run-the-gate-each", into="2026-09-01-run-the-gate")
    ]
    assert pairs(entries, frozenset(), NOW) == []


def lesson(id_: str, statement: str, guard: str = "", **fields: object) -> MemoryEntry:
    return entry(id_, statement, kind="lesson", guard=guard, **fields)


def test_a_lesson_its_guard_enforces_and_nobody_reviewed_for_a_month_retires_before_any_merge() -> (
    None
):
    entries = [
        lesson(
            "2026-08-12-close-the-ledger",
            "Close the ledger handle after reading it",
            "guarded_test",
        ),
        *many(
            ("2026-09-01-run-the-gate", "Run the gate before every push of a ticket branch"),
            ("2026-09-05-run-the-gate-each", "Run the gate before each push of the ticket branch"),
        ),
    ]
    assert proposals(entries, frozenset({"guarded_test"}), NOW) == [
        Retire(id="2026-08-12-close-the-ledger", guard="guarded_test"),
        Merge(from_id="2026-09-05-run-the-gate-each", into="2026-09-01-run-the-gate"),
    ]
    assert retire_reason("guarded_test") == "its guard guarded_test is a test now"


def test_a_lesson_reviewed_within_the_month_is_not_proposed_for_retirement() -> None:
    fresh = lesson("2026-08-12-close", "Close the ledger", "guarded_test", reviewed="2026-11-01")
    assert proposals([fresh], frozenset({"guarded_test"}), NOW) == []


def test_alike_entries_merge_into_the_earliest_and_each_later_one_is_taken_in_once() -> None:
    same = "Run the gate before every push of a ticket branch"
    entries = many(("2026-09-03-c", same), ("2026-09-01-a", same), ("2026-09-02-b", same))
    assert proposals(entries, frozenset(), NOW) == [
        Merge(from_id="2026-09-02-b", into="2026-09-01-a"),
        Merge(from_id="2026-09-03-c", into="2026-09-01-a"),
    ]


def test_entries_of_two_kinds_do_not_merge() -> None:
    same = "Run the gate before every push of a ticket branch"
    entries = [entry("2026-09-01-a", same), entry("2026-09-02-b", same, kind="decision")]
    assert proposals(entries, frozenset(), NOW) == []


def test_two_lessons_with_different_guards_do_not_merge_and_the_same_guard_does() -> None:
    same = "Run the gate before every push of a ticket branch"
    defined = frozenset({"one_test", "two_test"})
    differ = [
        lesson("2026-09-01-a", same, "one_test", reviewed="2026-11-01"),
        lesson("2026-09-02-b", same, "two_test", reviewed="2026-11-01"),
    ]
    assert proposals(differ, defined, NOW) == []
    equal = [
        lesson("2026-09-01-a", same, "one_test", reviewed="2026-11-01"),
        lesson("2026-09-02-b", same, "one_test", reviewed="2026-11-01"),
    ]
    assert proposals(equal, frozenset({"one_test"}), NOW) == [
        Merge(from_id="2026-09-02-b", into="2026-09-01-a")
    ]


def test_a_lesson_whose_guard_names_no_test_does_not_merge() -> None:
    same = "Run the gate before every push of a ticket branch"
    entries = [lesson("2026-09-01-a", same, "gone_test"), lesson("2026-09-02-b", same)]
    assert proposals(entries, frozenset(), NOW) == []
    blank = [lesson("2026-09-01-a", same), lesson("2026-09-02-b", same)]
    assert len(proposals(blank, frozenset(), NOW)) == 1


def test_four_of_seven_shared_words_is_not_alike_and_three_of_four_is() -> None:
    new = "Production errors do not become bug tickets"
    assert alike(new, "Production errors and alerts do not become tickets")
    assert not alike(new, "Production errors become very long tickets in lists")
    assert not alike(new, "Tickets become archived when merged")
    assert alike("Alpha beta gamma delta", "Alpha beta gamma epsilon")
    assert not alike("", "")


def test_a_new_title_asks_about_each_open_ticket_it_looks_like() -> None:
    open_tickets = [
        ("CF-1", "Production errors and alerts do not become tickets"),
        ("CF-2", "Tickets become archived when merged"),
        ("CF-5", "Production errors become very long tickets in lists"),
    ]
    asked = duplicate_questions("Production errors do not become bug tickets", open_tickets)
    assert len(asked) == 1
    question = asked[0]
    assert question.ticket_id == "CF-1"
    assert question.text == (
        "Is this the same change as CF-1 (Production errors and alerts do not become tickets)?"
    )
    assert [(c.text, c.recommended, c.reason) for c in question.choices] == [
        ("Merge into CF-1", True, "the titles share most of their words"),
        ("Keep both", False, "they are different changes"),
    ]


def test_a_title_like_no_open_ticket_asks_nothing() -> None:
    assert (
        duplicate_questions("Column scrollbars keep their padding", [("CF-1", "Other things")])
        == []
    )
    assert duplicate_questions("Anything at all", []) == []
