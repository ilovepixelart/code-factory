"""What a card says: checklist counts, trimmed description, due state, days in the column."""

from datetime import UTC, datetime

import pytest

from code_factory.board.rules.words import (
    checklist_counts,
    days_in_column,
    due_date,
    due_state,
    trim,
)

NOW = datetime(2026, 11, 23, 9, 30, tzinfo=UTC)


def test_the_sample_description_has_one_of_three_done() -> None:
    assert checklist_counts("- [x] one\n- [ ] two\n- [ ] three") == (1, 3)


@pytest.mark.parametrize(
    ("line", "counted"),
    [
        ("* [X] a", (1, 1)),
        ("  - [ ] x", (0, 1)),
        ("-[ ] x", (0, 0)),
        ("- [] x", (0, 0)),
        ("1. [ ] n", (0, 0)),
        ("text - [ ] x", (0, 0)),
    ],
)
def test_only_bullet_checkboxes_at_a_line_start_count(line: str, counted: tuple[int, int]) -> None:
    assert checklist_counts(line) == counted


def test_a_text_at_the_limit_is_kept_whole() -> None:
    assert trim("a" * 280, 280) == "a" * 280


def test_a_longer_text_is_cut_to_the_limit_with_an_ellipsis() -> None:
    assert trim("a" * 281, 280) == "a" * 279 + "…"


def test_multibyte_characters_count_as_one() -> None:
    assert trim("é" * 281, 280) == "é" * 279 + "…"


@pytest.mark.parametrize(
    ("due", "stage", "state"),
    [
        ("2026-11-22", "build", "overdue"),
        ("2026-11-23", "build", "soon"),
        ("2026-11-25", "build", "soon"),
        ("2026-11-26", "build", ""),
        ("2026-13-40", "build", ""),
        ("", "build", ""),
        ("2026-11-01", "merged", ""),
        ("2026-11-01", "released", ""),
    ],
)
def test_due_state_against_the_utc_day(due: str, stage: str, state: str) -> None:
    assert due_state(due, stage, NOW) == state


def test_due_date_is_the_day_or_none() -> None:
    assert (due_date("2026-10-10"), due_date(""), due_date("soon"), due_date("20261010")) == (
        "2026-10-10",
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    ("since", "now", "days"),
    [
        ("2026-11-20T12:00:00Z", datetime(2026, 11, 23, 11, 59, 59, tzinfo=UTC), 2),
        ("2026-11-20T12:00:00Z", datetime(2026, 11, 23, 12, 0, 0, tzinfo=UTC), 3),
        ("2026-11-23T12:00:01Z", datetime(2026, 11, 23, 12, 0, 0, tzinfo=UTC), -1),
        ("", NOW, None),
        ("not a time", NOW, None),
    ],
)
def test_days_in_column_floors_toward_negative_infinity(
    since: str, now: datetime, days: int | None
) -> None:
    assert days_in_column(since, now) == days
