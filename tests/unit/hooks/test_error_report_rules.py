"""A production error report: its fields, the refusal, and the release a new report follows."""

import pytest

from code_factory.hooks.models import ReleaseFact, ReportFields, Tie
from code_factory.hooks.rules.error_report import (
    DEFAULT_WATCH_DAYS,
    REFUSED,
    normalise,
    release_tie,
)

DAY = 86_400
NOW = 1_800_000_000.0


def test_a_report_gives_its_four_fields_as_trimmed_text() -> None:
    fields = normalise(
        {
            "fingerprint": "  checkout-500 ",
            "title": "Checkout answers 500",
            "message": "TypeError",
            "release": " 1.0.0 ",
        }
    )

    assert fields == ReportFields(
        fingerprint="checkout-500",
        title="Checkout answers 500",
        message="TypeError",
        release="1.0.0",
    )


def test_missing_fields_are_empty_and_a_number_is_its_text() -> None:
    fields = normalise({"fingerprint": 42})

    assert fields == ReportFields(fingerprint="42", title="", message="", release="")


def test_a_field_that_is_a_list_or_an_object_reads_as_empty() -> None:
    fields = normalise({"fingerprint": "f", "title": ["x"], "message": {"a": 1}})

    assert isinstance(fields, ReportFields)
    assert (fields.title, fields.message) == ("", "")


def test_a_secret_in_the_message_is_masked() -> None:
    fields = normalise({"fingerprint": "f", "message": "failed with sk-abc123DEF at cart.ts"})

    assert isinstance(fields, ReportFields)
    assert fields.message == "failed with [redacted] at cart.ts"


def test_a_field_is_cut_to_two_thousand_characters() -> None:
    fields = normalise({"fingerprint": "f", "message": "m" * 2_500})

    assert isinstance(fields, ReportFields)
    assert fields.message == "m" * 2_000
    assert normalise({"fingerprint": "f", "message": "m" * 2_000}) == ReportFields(  # the boundary
        fingerprint="f", title="", message="m" * 2_000, release=""
    )


def test_characters_that_show_as_nothing_are_dropped_before_the_field_is_read() -> None:
    fields = normalise(
        {"fingerprint": "ab" + chr(0x200B) + "cd", "message": "ig" + chr(0x200B) + "nore"}
    )

    assert isinstance(fields, ReportFields)
    assert (fields.fingerprint, fields.message) == ("abcd", "ignore")


@pytest.mark.parametrize(
    "report",
    [
        {},
        {"fingerprint": ""},
        {"fingerprint": "   "},
        {"fingerprint": "a\nb"},
        {"fingerprint": "a\rb"},
        {"fingerprint": "a" + chr(0x2028) + "b"},
        {"fingerprint": "a\x85b"},
        {"fingerprint": ["x"]},
        {"fingerprint": None, "message": "m"},
        {"fingerprint": chr(0x200B)},
        [],
        "text",
        None,
        3,
    ],
)
def test_a_report_without_a_one_line_fingerprint_is_refused(report: object) -> None:
    assert normalise(report) == REFUSED == "a report needs a one-line fingerprint"


RELEASES = [
    ReleaseFact(version="0.9.0", at=NOW - 40 * DAY, tickets=["CF-3"]),
    ReleaseFact(version="1.0.0", at=NOW - 3_600, tickets=["CF-1", "CF-2"]),
]


def test_a_report_inside_the_window_of_the_newest_release_names_its_tickets() -> None:
    assert release_tie(RELEASES, "", NOW, DEFAULT_WATCH_DAYS) == Tie(
        caused_by=["CF-1", "CF-2"],
        paragraph="Seen within the verification window of release 1.0.0, which shipped CF-1, CF-2.",
    )


def test_a_report_naming_its_release_names_that_release_even_outside_the_window() -> None:
    assert release_tie(RELEASES, "0.9.0", NOW, DEFAULT_WATCH_DAYS) == Tie(
        caused_by=["CF-3"], paragraph="Reported against release 0.9.0, which shipped CF-3."
    )


def test_a_name_that_matches_no_release_falls_back_to_the_window() -> None:
    tie = release_tie(RELEASES, "7.7.7", NOW, DEFAULT_WATCH_DAYS)

    assert tie is not None
    assert tie.paragraph.startswith("Seen within the verification window of release 1.0.0")


def test_a_name_with_a_line_break_counts_as_no_name() -> None:
    odd = ReleaseFact(version="0.8.0\nx", at=NOW - 50 * DAY, tickets=["CF-9"])

    tie = release_tie([odd, *RELEASES], "0.8.0\nx", NOW, DEFAULT_WATCH_DAYS)

    assert tie is not None
    assert tie.paragraph.startswith("Seen within")


def test_the_window_closes_one_second_after_watch_days() -> None:
    inside = [ReleaseFact(version="1.0.0", at=NOW - 7 * DAY, tickets=["CF-1"])]
    outside = [ReleaseFact(version="1.0.0", at=NOW - 7 * DAY - 1, tickets=["CF-1"])]

    assert release_tie(inside, "", NOW, 7) is not None
    assert release_tie(outside, "", NOW, 7) is None


def test_the_window_follows_watch_days() -> None:
    two_days = [ReleaseFact(version="1.0.0", at=NOW - 2 * DAY, tickets=["CF-1"])]

    assert release_tie(two_days, "", NOW, 1) is None
    assert release_tie(two_days, "", NOW, 2) is not None


def test_a_watch_of_zero_days_ties_no_unnamed_report() -> None:
    fresh = [ReleaseFact(version="1.0.0", at=NOW, tickets=["CF-1"])]

    assert release_tie(fresh, "", NOW, 0) is None
    assert release_tie(fresh, "1.0.0", NOW, 0) is not None


def test_a_release_with_no_tickets_ties_nothing() -> None:
    empty = [ReleaseFact(version="1.0.0", at=NOW, tickets=[])]

    assert release_tie(empty, "", NOW, 7) is None
    assert release_tie(empty, "1.0.0", NOW, 7) is None
    assert release_tie([], "", NOW, 7) is None


def test_the_default_watch_is_seven_days() -> None:
    assert DEFAULT_WATCH_DAYS == 7
