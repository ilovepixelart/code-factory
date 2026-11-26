"""The field rules of a ticket write, with the sentences the app shows.

Expected values are the recorded golden answers (G[n] of tests/support/golden/formats/writes), the
previous implementation's tests, and hand-worked cases.
"""

import pytest

from code_factory.ticket_writes.rules import (
    budget_text,
    card_fields,
    normalised_list,
    one_line,
    parallel_text,
    unknown_fields,
)


def test_unknown_fields_are_sorted_and_listed_once() -> None:
    assert (
        unknown_fields(["zeta", "alpha", "zeta"], {"title"}) == "unknown fields ['alpha', 'zeta']"
    )


def test_known_fields_are_not_refused() -> None:
    assert unknown_fields(["title"], {"title", "type"}) is None


@pytest.mark.parametrize("brk", ["\n", "\r", "\v", "\f", "\x85", chr(0x2028), chr(0x2029)])
def test_a_line_break_of_any_class_is_refused_outside_the_description(brk: str) -> None:
    assert one_line([("title", f"a{brk}b")]) == "title holds a line break"


def test_the_description_may_hold_line_breaks_and_a_tab_is_no_line_break() -> None:
    assert one_line([("description", "a\nb"), ("title", "a\tb")]) is None


def test_the_first_field_with_a_line_break_is_named() -> None:
    pairs = [("title", "ok"), ("assignee", "x\ny"), ("tests", "p\nq")]
    assert one_line(pairs) == "assignee holds a line break"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("a, b,", "a, b"), (" CF-1 ,, CF-3", "CF-1, CF-3"), ("", ""), (" , ", "")],
)
def test_a_list_is_split_stripped_and_joined(text: str, expected: str) -> None:
    assert normalised_list(text) == expected


def test_card_fields_normalise_what_was_given_only() -> None:
    values = {"labels": "a, b,", "priority": "high", "due": "2026-11-01", "assignee": " ann "}
    assert card_fields(values) == {
        "labels": "a, b",
        "priority": "high",
        "due": "2026-11-01",
        "assignee": "ann",
    }


@pytest.mark.parametrize(
    ("values", "sentence"),
    [
        ({"priority": "soon"}, "unknown priority soon"),
        ({"due": "2026-13-01"}, "bad due date 2026-13-01"),
        ({"archived": "maybe"}, "bad archived maybe"),
    ],
)
def test_card_fields_refuse_with_the_golden_sentences(
    values: dict[str, str], sentence: str
) -> None:
    assert card_fields(values) == sentence


def test_card_fields_check_priority_then_due_then_archived() -> None:
    both = {"archived": "maybe", "due": "x", "priority": "soon"}
    assert card_fields(both) == "unknown priority soon"
    assert card_fields({"archived": "maybe", "due": "x"}) == "bad due date x"


@pytest.mark.parametrize(
    ("given", "stored"),
    [("ON", "true"), ("True", "true"), ("false", ""), ("", ""), ("on", "true")],
)
def test_archived_reads_true_false_and_on_in_any_case(given: str, stored: str) -> None:
    assert card_fields({"archived": given}) == {"archived": stored}


def test_an_empty_priority_and_due_clear_the_field() -> None:
    assert card_fields({"priority": "", "due": ""}) == {"priority": "", "due": ""}


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("0", "0"),
        ("1000", "1000"),
        (" 3.5 ", "3.5"),
        ("", ""),
        ("   ", ""),
        ("1e3", "1000"),
        (".5", "0.5"),
        ("5.", "5"),
        ("+2", "2"),
        ("1.50", "1.50"),
    ],
)
def test_a_budget_is_a_non_negative_finite_number_stored_as_plain_decimal(
    given: str, stored: str
) -> None:
    assert budget_text(given) == stored


@pytest.mark.parametrize(
    "given", ["abc", "-1", "1__0", "1_0", "٣", "inf", "nan", "1e400", "--1", "1,5", "0x10"]
)
def test_a_budget_that_is_not_ascii_decimal_or_not_finite_is_refused(given: str) -> None:
    assert budget_text(given) == "budget must be a number of dollars"


@pytest.mark.parametrize(
    ("given", "stored"), [("", ""), ("1", "1"), ("4", "4"), ("02", "2"), (" 3 ", "3")]
)
def test_parallel_is_one_to_four(given: str, stored: str) -> None:
    assert parallel_text(given) == stored


@pytest.mark.parametrize("given", ["0", "5", "7", "+2", "2.0", "-1", "٢", "a", "00"])
def test_parallel_outside_one_to_four_or_not_ascii_digits_is_refused(given: str) -> None:
    assert parallel_text(given) == "parallel must be 1 to 4"


@pytest.mark.parametrize(("given", "stored"), [("-0", "0"), ("+0.00", "0.00"), ("-0.0", "0.0")])
def test_a_zero_budget_never_keeps_its_sign(given: str, stored: str) -> None:
    assert budget_text(given) == stored


@pytest.mark.parametrize("given", ["1e-31", "1e31", "1e-999999999999", "0e999999999", "9" * 40])
def test_a_budget_whose_plain_form_would_be_huge_is_refused(given: str) -> None:
    assert budget_text(given) == "budget must be a number of dollars"


def test_a_budget_at_the_edge_of_the_range_is_written_out() -> None:
    assert budget_text("1e30") == "1" + "0" * 30
    assert budget_text("1e-30") == "0." + "0" * 29 + "1"


def test_a_parallel_count_of_thousands_of_digits_is_refused_or_read_without_converting_it() -> None:
    assert parallel_text("9" * 5000) == "parallel must be 1 to 4"
    assert parallel_text("0" * 5000 + "2") == "2"
    assert parallel_text("0" * 5000) == "parallel must be 1 to 4"


@pytest.mark.parametrize(
    "given", ["1e999999999999999999999999999", "10." + "0" * 39 + "1", "1e-9999999999999999999999"]
)
def test_a_budget_past_the_decimal_range_is_refused_not_raised(given: str) -> None:
    assert budget_text(given) == "budget must be a number of dollars"
