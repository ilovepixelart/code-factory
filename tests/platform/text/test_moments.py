import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from code_factory.platform.text import (
    day_minute,
    day_text,
    epoch_day,
    is_iso_date,
    iso_date_days,
    stamp,
    stamp_moment,
)

DISPLAY = json.loads(
    (Path(__file__).resolve().parents[2] / "golden/formats/display/cases.golden.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (0.0, "1970-01-01T00:00:00Z"),
        (1790001000.0, "2026-09-21T14:30:00Z"),
        (1790001000.9999995, "2026-09-21T14:30:01Z"),
        (1790001000.9999993, "2026-09-21T14:30:00Z"),
        (-0.5, "1969-12-31T23:59:59Z"),
        (-62135596800.0, "0001-01-01T00:00:00Z"),
    ],
)
def test_stamp_of_a_float_is_utc_seconds(moment: float, expected: str) -> None:
    assert stamp(moment) == expected


def test_stamp_of_a_datetime_equals_the_float_for_whole_seconds() -> None:
    moment = datetime(2026, 9, 21, 14, 30, tzinfo=UTC)
    assert stamp(moment) == stamp(1790001000.0) == "2026-09-21T14:30:00Z"


def test_stamp_converts_an_offset_datetime_and_drops_the_fraction() -> None:
    plus_two = timezone(timedelta(hours=2))
    assert (
        stamp(datetime(2026, 9, 21, 16, 30, 0, 999999, tzinfo=plus_two)) == "2026-09-21T14:30:00Z"
    )


def test_stamp_outside_years_1_to_9999_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="year"):
        stamp(253402300800.0)


@pytest.mark.parametrize("moment", [0.0, 1790001000.0, -1000.0, 1e9, -62135596800.0])
def test_stamp_moment_round_trips_whole_seconds(moment: float) -> None:
    assert stamp_moment(stamp(moment)) == moment


@pytest.mark.parametrize(
    "text",
    [
        "2026-02-30T00:00:00Z",
        "2026-09-21T24:00:00Z",
        "2026-09-21T14:30:62Z",
        "2026-09-21 14:30:00Z",
        "٢٠٢٦-09-21T14:30:00Z",
        "0000-09-21T14:30:00Z",
        "2026-09-21T14:60:00Z",
        "2026-09-21T14:30:00",
        "",
    ],
)
def test_stamp_moment_refuses_a_malformed_text(text: str) -> None:
    assert stamp_moment(text) is None


@pytest.mark.parametrize(
    ("text", "second"), [("2026-09-21T14:30:60Z", 60), ("2026-09-21T14:30:61Z", 61)]
)
def test_stamp_moment_accepts_leap_seconds(text: str, second: int) -> None:
    assert stamp_moment(text) == 1790001000.0 + second


def test_epoch_day_floors_to_the_utc_day() -> None:
    assert epoch_day(0.0) == 719163
    assert epoch_day(-0.5) == 719162
    assert epoch_day(datetime(1970, 1, 2, tzinfo=UTC)) == 719164


def test_dates_follow_the_previous_golden() -> None:
    for row in DISPLAY["days"]:
        days = iso_date_days(row["raw"])
        if row["date"] is None:
            assert days is None
            assert not is_iso_date(row["raw"])
        else:
            assert days is not None
            assert day_text(days) == row["date"]
            assert is_iso_date(row["raw"])


def test_a_date_with_trailing_text_is_still_a_date_and_year_zero_is_not() -> None:
    assert is_iso_date("20261004ab")
    assert not is_iso_date("0000-01-01")


def test_day_minute_has_unpadded_day_and_english_month() -> None:
    assert day_minute(1790001000) == "21 Sep 14:30"
    assert day_minute(0) == "1 Jan 00:00"


def test_a_moment_whose_utc_value_leaves_years_1_to_9999_is_a_value_error() -> None:
    early = datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=5)))
    late = datetime(9999, 12, 31, 23, tzinfo=timezone(timedelta(hours=-5)))
    for moment in (early, late):
        with pytest.raises(ValueError, match="outside the years 1 to 9999"):
            stamp(moment)


def test_epoch_day_of_an_offset_datetime_is_its_utc_day() -> None:
    assert epoch_day(datetime(1970, 1, 1, 23, tzinfo=timezone(timedelta(hours=-5)))) == 719164
    assert epoch_day(datetime(1970, 1, 2, 1, tzinfo=timezone(timedelta(hours=5)))) == 719163
