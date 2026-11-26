"""The pure ticket rules, with expected values worked out by hand from the board's rules."""

import pytest

from code_factory.platform.errors import BadRequestError
from code_factory.tickets.models import Column, PullRequestState, TicketFields
from code_factory.tickets.rules import (
    MAX_NUMBER,
    branch_refusal,
    clean_fields,
    column_of,
    ticket_id,
    ticket_number,
)


def test_an_id_is_the_prefix_and_the_number() -> None:
    assert ticket_id(1449) == "CF-1449"
    assert ticket_number("CF-1449") == 1449


@pytest.mark.parametrize(
    "text",
    [
        "CF-",
        "CF-0",
        "cf-12",
        "XY-12",
        "CF-12a",
        "CF-+3",
        "CF-٣",
        "12",
    ],
)
def test_an_id_that_is_not_cf_and_a_positive_number_is_refused(text: str) -> None:
    with pytest.raises(BadRequestError, match=r"is not a ticket id CF-<n>"):
        ticket_number(text)


def test_a_number_beyond_the_column_is_above_the_largest_without_being_parsed() -> None:
    assert ticket_number("CF-9223372036854775807") == MAX_NUMBER
    assert ticket_number("CF-9223372036854775808") > MAX_NUMBER
    assert ticket_number("CF-" + "9" * 5000) > MAX_NUMBER


@pytest.mark.parametrize(
    ("branch", "pull_request", "merged", "column"),
    [
        ("", None, False, Column.SPEC),
        ("ticket/cf-7", None, False, Column.BUILD),
        ("ticket/cf-7", PullRequestState.CLOSED, False, Column.BUILD),
        ("ticket/cf-7", PullRequestState.OPEN, False, Column.REVIEW),
        ("ticket/cf-7", PullRequestState.MERGED, False, Column.MERGED),
        ("ticket/cf-7", PullRequestState.OPEN, True, Column.MERGED),
        ("", None, True, Column.MERGED),
    ],
)
def test_the_column_is_read_from_the_branch_the_pull_request_and_the_merge(
    branch: str, pull_request: PullRequestState | None, merged: bool, column: Column
) -> None:
    assert column_of(branch, pull_request, merged) is column


@pytest.mark.parametrize(
    ("name", "why"),
    [
        ("@", "@ is git's name for the checked-out commit"),
        ("HEAD", "HEAD is git's name for the checked-out commit"),
        ("FETCH_HEAD", "it looks like a top-level ref such as FETCH_HEAD"),
        ("a" * 40, "it is a full commit id"),
        ("Origin/main", "it starts with origin/"),
        ("refs/heads/x", "it starts with refs/"),
        ("-x", "it starts with -"),
        ("café", "it holds a non-ASCII character"),
        ("a b", "it holds a space"),
        ("a~1", "it holds ~"),
        ("a..b", "it holds .."),
        ("a@{1}", "it holds @{"),
        ("/a", "it starts with /"),
        ("a/", "it ends with /"),
        ("a//b", "it holds //"),
        ("a.", "it ends with ."),
        ("a/.b", "a part of it starts with ."),
        ("a.lock/b", "a part of it ends with .lock"),
    ],
)
def test_a_branch_git_would_read_as_something_else_is_refused(name: str, why: str) -> None:
    refusal = branch_refusal(name)
    assert refusal is not None
    assert refusal.startswith(why)


@pytest.mark.parametrize("name", ["ticket/cf-7", "fix/CF-7-thing", "a.b", "a" * 39, "my_HEAD"])
def test_a_plain_branch_name_is_taken(name: str) -> None:
    assert branch_refusal(name) is None


def test_given_fields_are_normalised_and_unset_ones_left_out() -> None:
    fields = TicketFields(
        title="  A title ",
        labels=[" ui", "", "agents "],
        due="2026-10-04",
        budget=" 5 ",
        parallel="2",
        parent="CF-1",
        blocked_by=["CF-1", " CF-2 "],
    )
    assert clean_fields(fields) == {
        "title": "A title",
        "labels": ["ui", "agents"],
        "due": "2026-10-04",
        "budget": "5",
        "parallel": "2",
        "parent": 1,
        "blocked_by": [1, 2],
    }


def test_empty_optional_values_clear_the_field() -> None:
    fields = TicketFields(due="", budget="", parallel="", parent="")
    assert clean_fields(fields) == {"due": "", "budget": "", "parallel": "", "parent": None}


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        (TicketFields(title=" "), "a ticket needs a title"),
        (TicketFields(title="one\ntwo"), "a title is one line"),
        (TicketFields(due="2026-13-01"), "bad due date 2026-13-01"),
        (TicketFields(due="04.10.2026"), "bad due date 04.10.2026"),
        (TicketFields(budget="-1"), "bad budget -1"),
        (TicketFields(budget="nan"), "bad budget nan"),
        (TicketFields(parallel="1_0"), "bad parallel 1_0"),
        (TicketFields(parent="WX-1"), "'WX-1' is not a ticket id"),
        (TicketFields(caused_by=["CF-x"]), "'CF-x' is not a ticket id"),
    ],
)
def test_a_bad_field_value_is_refused_with_its_name(fields: TicketFields, problem: str) -> None:
    with pytest.raises(BadRequestError, match=problem):
        clean_fields(fields)
