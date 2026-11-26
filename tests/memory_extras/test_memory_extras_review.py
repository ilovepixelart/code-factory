"""Whether an entry still holds: guard, stale, due, overdue, incomplete, loaded, lapsed, unused."""

from datetime import UTC, date, datetime

import pytest

from code_factory.memory_extras.rules import (
    guard_state,
    incomplete,
    lapsed,
    loaded,
    overdue,
    review_due,
    stale,
    unused,
)
from code_factory.platform.text import epoch_day
from memory_extras_values import entry


def day(text: str) -> int:
    return epoch_day(datetime.combine(date.fromisoformat(text), datetime.min.time(), UTC))


def lesson(guard: str = "", **fields: object):  # noqa: ANN201
    return entry("2026-10-01-lesson", "A lesson", kind="lesson", guard=guard, **fields)


def test_guard_states_follow_the_defined_tests() -> None:
    defined = frozenset({"a_form_post_changes_nothing"})
    rule = entry(guard="a_form_post_changes_nothing")
    states = [
        guard_state(lesson("a_form_post_changes_nothing"), defined),
        guard_state(lesson("test_deleted_long_ago"), defined),
        guard_state(lesson(" "), defined),
        guard_state(rule, defined),
    ]
    assert states == ["enforced", "missing", "none", ""]


def test_an_entry_unreviewed_for_more_than_30_days_is_stale() -> None:
    today = day("2026-10-31")
    reviewed = lambda d: lesson(reviewed=d)  # noqa: E731
    never = entry("2026-09-30-never", kind="lesson")
    found = [
        stale(reviewed("2026-09-30"), today),
        stale(reviewed("2026-10-01"), today),
        stale(reviewed("2026-10-02"), today),
        stale(never, today),
    ]
    assert found == [True, False, False, True]


def test_a_review_that_is_not_a_date_is_never_stale_nor_due() -> None:
    odd = lesson(reviewed="garbage")
    assert not stale(odd, day("2099-01-01"))
    assert review_due(odd) == ""
    assert not overdue(odd, day("2099-01-01"))


@pytest.mark.parametrize(
    ("written", "reviewed", "due"),
    [
        ("2026-09-01", "", "2026-11-30"),
        ("2026-01-01", "2026-06-01", "2026-08-30"),
        ("2026-11-10", "", "2027-02-08"),
        ("2024-12-01", "", "2025-03-01"),
    ],
)
def test_review_is_due_ninety_days_after_the_last_review(
    written: str, reviewed: str, due: str
) -> None:
    assert review_due(entry(f"{written}-x", reviewed=reviewed)) == due


def test_an_entry_is_overdue_only_after_its_due_day_and_a_proposal_never() -> None:
    today = day("2026-09-21")
    found = [
        overdue(entry("2026-06-23-a"), today),
        overdue(entry("2026-06-24-b"), today),
        overdue(entry("2026-06-22-c"), today),
        overdue(entry("2026-01-01-d", proposed=True), today),
    ]
    assert found == [False, False, True, False]


def test_an_entry_lacking_statement_why_or_source_is_incomplete() -> None:
    assert not incomplete(entry(why="because", source="chat"))
    assert incomplete(entry(why="", source="chat"))
    assert incomplete(entry(why="because", source=" "))
    assert incomplete(entry(statement=" ", why="because"))


def test_a_lesson_its_guard_enforces_is_not_loaded_and_neither_is_a_retired_or_proposed_one() -> (
    None
):
    defined = frozenset({"guarded"})
    assert loaded(lesson("unknown"), defined)
    assert not loaded(lesson("guarded"), defined)
    assert loaded(entry(guard="guarded"), defined)  # only a lesson is enforced by its guard
    assert not loaded(entry(proposed=True), defined)
    assert not loaded(entry(retired="done"), defined)


def merged(*ids: str):  # noqa: ANN201
    return lambda ticket: ticket in ids


def test_an_entry_is_delivered_through_its_expires_day_and_not_after() -> None:
    ending = entry(expires="2026-11-15")
    assert not lapsed(ending, "2026-11-15", merged())
    assert lapsed(ending, "2026-11-16", merged())


def test_an_entry_ends_when_its_until_ticket_has_merged() -> None:
    ending = entry(until="CF-9")
    assert lapsed(ending, "2026-11-10", merged("CF-9"))
    assert not lapsed(ending, "2026-11-10", merged("CF-8"))


def test_an_entry_with_neither_expires_nor_until_never_lapses() -> None:
    assert not lapsed(entry(), "2999-01-01", merged("CF-9"))


def test_an_entry_not_received_for_more_than_30_days_is_unused() -> None:
    today = day("2026-11-10")
    assert not unused(entry("2026-11-10-a"), None, today)
    assert not unused(entry("2026-10-11-a"), None, today)
    assert unused(entry("2026-10-10-a"), None, today)
    old = entry("2026-01-01-old")
    assert not unused(old, "2026-11-01", today)
    assert not unused(old, "2026-10-11", today)
    assert unused(old, "2026-10-10", today)
    assert unused(old, "2026-10-01", today)


def test_a_last_receipt_that_is_not_a_day_is_never_unused() -> None:
    assert not unused(entry("2026-01-01-old"), "garbage", day("2026-11-10"))
