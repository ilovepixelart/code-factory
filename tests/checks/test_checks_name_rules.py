"""Hand-worked cases for the checks module's naming and limit rules."""

from datetime import timedelta

import pytest

from code_factory.checks.rules import cache_key, checks_limit, log_name, log_name_any, log_name_ok


@pytest.mark.parametrize(
    ("configured", "expected"),
    [(None, timedelta(seconds=3600)), (0, None), (120, timedelta(seconds=120))],
)
def test_the_limit_is_an_hour_unset_none_at_zero_and_the_seconds_given(
    configured: int | None, expected: timedelta | None
) -> None:
    assert checks_limit(configured) == expected


@pytest.mark.parametrize(
    ("ticket", "key"),
    [
        ("CF-12", "CF-12"),
        ("a_b-C9", "a_b-C9"),
        ("../../etc", "______etc"),
        ("", ""),
        ("a b/c", "a_b_c"),
    ],
)
def test_a_cache_key_replaces_every_character_outside_letters_digits_dash_and_underscore(
    ticket: str, key: str
) -> None:
    assert cache_key(ticket) == key


def test_a_log_is_named_for_the_repository_the_subject_and_the_second() -> None:
    assert log_name("sample", "CF-12", 1700000000) == "sample-CF-12-1700000000.log"


@pytest.mark.parametrize(
    "name",
    [
        "sample-CF-12-1700000000.log",
        "sample-CF-12-0.log",
    ],
)
def test_a_log_of_the_ticket_is_accepted(name: str) -> None:
    assert log_name_ok(name, "sample", "CF-12")


@pytest.mark.parametrize(
    "name",
    [
        "sample-CF-13-17.log",  # another ticket
        "other-CF-12-17.log",  # another repository
        "sample-CF-12-.log",  # no second
        "sample-CF-12-12a.log",  # not digits
        "sample-CF-12-17.txt",  # not a log
        "sample-CF-12-1-7.log",  # more than a second
        "sample-CF-1-17.log",  # CF-1 is not CF-12
    ],
)
def test_a_log_of_another_ticket_or_repository_or_a_malformed_name_is_refused(name: str) -> None:
    assert not log_name_ok(name, "sample", "CF-12")


def test_a_log_name_of_ticket_one_does_not_open_for_ticket_twelve() -> None:
    assert not log_name_ok("sample-CF-12-17.log", "sample", "CF-1")


@pytest.mark.parametrize(
    "name",
    ["sample-CF-12-1700000000.log", "sample-main-17.log", "my-repo-CF-3-0.log", "r-ENG2-5-1.log"],
)
def test_a_log_name_of_any_ticket_or_main_is_one_the_stages_may_read(name: str) -> None:
    assert log_name_any(name)


@pytest.mark.parametrize(
    "name",
    [
        "../x-CF-1-1.log",
        "sample-CF-1-1.txt",
        "sample-CF-1-x.log",
        "notes.log",
        "a/b-CF-1-1.log",
        "",
    ],
)
def test_other_names_are_never_read_by_the_stages(name: str) -> None:
    assert not log_name_any(name)
