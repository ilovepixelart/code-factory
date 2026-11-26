"""Bulk choice, bulk checks, bulk changes and notices (G[40] to G[53])."""

import pytest

from code_factory.ticket_writes.models import BulkChoice
from code_factory.ticket_writes.rules import (
    bulk_change,
    bulk_choice,
    bulk_notice,
    check_bulk,
    drop_groups,
    limit_value,
    rank_positions,
    revert_conflict,
)
from write_values import core

ONE_ACTION = "one action and at least one ticket"


def test_one_action_and_its_tickets_make_a_choice() -> None:
    body = {"tickets": ["sample/CF-2", " second/CF-1 "], "priority": " low "}
    assert bulk_choice(body) == BulkChoice(
        field="priority", value="low", tickets=["sample/CF-2", "second/CF-1"]
    )


@pytest.mark.parametrize("name", ["stage", "priority", "label", "archived"])
def test_each_of_the_four_actions_is_found(name: str) -> None:
    choice = bulk_choice({"tickets": ["a/CF-1"], name: "x"})
    assert isinstance(choice, BulkChoice)
    assert (choice.field, choice.value) == (name, "x")


def test_an_empty_value_still_counts_as_given() -> None:
    choice = bulk_choice({"tickets": ["a/CF-1"], "archived": ""})
    assert isinstance(choice, BulkChoice)
    assert (choice.field, choice.value) == ("archived", "")


@pytest.mark.parametrize(
    "body",
    [
        {"tickets": ["a/CF-1"], "stage": "build", "priority": "low"},
        {"tickets": [], "priority": "low"},
        {"tickets": [" ", ""], "priority": "low"},
        {"priority": "low"},
        {"tickets": ["a/CF-1"]},
        {"tickets": "a/CF-1", "priority": "low"},
        {"tickets": ["a/CF-1", 3], "priority": "low"},
    ],
)
def test_two_actions_or_no_tickets_are_refused(body: dict[str, object]) -> None:
    assert bulk_choice(body) == ONE_ACTION


@pytest.mark.parametrize(
    ("field", "value", "sentence"),
    [
        ("stage", "later", "unknown stage later"),
        ("priority", "soon", "unknown priority soon"),
        ("label", "a, b", "a label is one word or phrase"),
        ("label", "", "a label is one word or phrase"),
        ("archived", "yes", "archived is true or empty"),
    ],
)
def test_a_bulk_value_is_refused_with_its_sentence(field: str, value: str, sentence: str) -> None:
    assert check_bulk(field, value) == sentence


@pytest.mark.parametrize("field", ["title", "rank", "branch", "unknown", ""])
def test_a_bulk_on_a_field_that_is_no_action_is_refused(field: str) -> None:
    assert check_bulk(field, "x") == ONE_ACTION


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stage", "spec"),
        ("stage", "merged"),
        ("priority", "urgent"),
        ("priority", ""),
        ("label", "ops"),
        ("label", "two words"),
        ("archived", "true"),
        ("archived", ""),
    ],
)
def test_a_legitimate_bulk_value_is_not_refused(field: str, value: str) -> None:
    assert check_bulk(field, value) is None


def test_bulk_priority_gives_the_new_and_the_old_text() -> None:
    assert bulk_change(core(1, priority="high"), "priority", "low") == ("priority", "low", "high")


def test_bulk_label_appends_once_and_keeps_the_list_normalised() -> None:
    assert bulk_change(core(1, labels=["a"]), "label", "ops") == ("labels", "a, ops", "a")
    assert bulk_change(core(1, labels=["a", "ops"]), "label", "ops") == (
        "labels",
        "a, ops",
        "a, ops",
    )
    assert bulk_change(core(1), "label", "ops") == ("labels", "ops", "")


def test_bulk_archive_and_restore_swap_the_flag_text() -> None:
    assert bulk_change(core(1), "archived", "true") == ("archived", "true", "")
    assert bulk_change(core(1, archived=True), "archived", "") == ("archived", "", "true")


@pytest.mark.parametrize(
    ("field", "value", "count", "notice"),
    [
        ("stage", "spec", 2, "Moved 2 tickets to Spec"),
        ("label", "ops", 2, "Labelled 2 tickets ops"),
        ("archived", "true", 1, "Archived 1 ticket"),
        ("archived", "", 2, "Restored 2 tickets"),
        ("priority", "low", 2, "Set low priority on 2 tickets"),
        ("priority", "low", 1, "Set low priority on 1 ticket"),
        ("stage", "build", 1, "Moved 1 ticket to Build"),
    ],
)
def test_the_notice_counts_in_singular_and_plural(
    field: str, value: str, count: int, notice: str
) -> None:
    assert bulk_notice(field, value, count) == notice


def test_drop_entries_group_by_repository_in_first_seen_order_keeping_each_sequence() -> None:
    order = ["sample/CF-3", " second/CF-1", "sample/CF-2 ", "second/CF-4"]
    assert drop_groups(order) == [("sample", ["CF-3", "CF-2"]), ("second", ["CF-1", "CF-4"])]


def test_a_drop_entry_without_a_slash_is_a_repository_with_an_empty_id() -> None:
    assert drop_groups(["lonely"]) == [("lonely", [""])]


def test_ranks_count_from_one_and_leave_out_unknown_and_placed_ids() -> None:
    # G[28]: CF-3 is dropped first, CF-2 already holds 2, CF-9 is no ticket.
    ranks = {"CF-3": 1, "CF-2": 2}
    assert rank_positions(["CF-3", "CF-2"], ranks) == {}
    assert rank_positions(["CF-3", "CF-9", "CF-2"], ranks) == {"CF-2": 3}
    assert rank_positions(["CF-2", "CF-3"], ranks) == {"CF-2": 1, "CF-3": 2}
    assert rank_positions(["CF-3", "CF-2"], {"CF-3": 0, "CF-2": 2}) == {"CF-3": 1}


def test_the_position_counts_unknown_ids_too() -> None:
    assert rank_positions(["CF-9", "CF-2"], {"CF-2": 0}) == {"CF-2": 2}


@pytest.mark.parametrize(("raw", "expected"), [(1, 1), (3, 3), (None, None), (100, 100)])
def test_a_limit_is_a_positive_whole_number_or_null(raw: object, expected: int | None) -> None:
    assert limit_value(raw) == expected


def test_a_limit_is_at_most_what_the_column_stores() -> None:
    assert limit_value(2**31 - 1) == 2**31 - 1
    assert limit_value(2**31) == "a limit must be a positive whole number"


@pytest.mark.parametrize("raw", [0, -1, 2.5, "3", "many", "", True, False, [1], {}])
def test_any_other_limit_is_refused(raw: object) -> None:
    assert limit_value(raw) == "a limit must be a positive whole number"


def test_a_guarded_field_that_changed_names_what_it_is_now() -> None:
    op = {"id": "CF-2", "expect": {"priority": "low"}}
    assert revert_conflict(op, {"priority": "high"}) == (
        "CF-2 priority changed since: it is high now, not low as the change left it"
    )


def test_a_guarded_field_that_still_holds_does_not_conflict() -> None:
    assert (
        revert_conflict({"id": "CF-2", "expect": {"priority": "low"}}, {"priority": "low"}) is None
    )
    assert revert_conflict({"id": "CF-2", "expect": {}}, {"priority": "anything"}) is None


def test_the_first_guarded_field_that_changed_is_named() -> None:
    op = {"id": "CF-2", "expect": {"labels": "a", "priority": "low"}}
    assert revert_conflict(op, {"labels": "b", "priority": "high"}) == (
        "CF-2 labels changed since: it is b now, not a as the change left it"
    )
