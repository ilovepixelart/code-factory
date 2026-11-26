"""F1: the range of a read, with expected values worked by hand from the spec's section 3."""

from datetime import UTC, datetime

import pytest

from code_factory.factory.rules.period import period
from code_factory.platform.errors import BadRequestError
from factory_values import DAY, FROM, NOW, T0, TO


def test_the_clock_constant_is_the_first_of_november() -> None:
    assert datetime(2026, 11, 1, tzinfo=UTC).timestamp() == T0


def test_a_date_is_midnight_utc_and_a_week_is_604800_seconds() -> None:
    got = period("2026-11-01", "2026-11-08", NOW)
    assert (got.from_, got.to, got.now) == (T0, T0 + 604800, NOW)


def test_epoch_seconds_and_dates_and_rfc_3339_agree() -> None:
    forms = [
        (str(int(FROM)), str(int(TO))),
        ("2026-11-01", "2026-11-08"),
        ("2026-11-01T00:00:00Z", "2026-11-08T00:00:00+00:00"),
    ]
    assert {(period(f, t, NOW).from_, period(f, t, NOW).to) for f, t in forms} == {(FROM, TO)}


@pytest.mark.parametrize(
    "marker", ["2026-11-01T00:00:00z", "2026-11-01t00:00:00Z", "2026-11-01 00:00:00Z"]
)
def test_the_lowercase_and_spaced_forms_rfc_3339_allows_are_accepted(marker: str) -> None:
    assert period(marker, "2026-11-08", NOW).from_ == T0


def test_an_instant_with_an_offset_is_converted_to_utc() -> None:
    got = period("2026-11-01T02:00:00+02:00", "2026-11-08T00:00:00-01:00", NOW)
    assert (got.from_, got.to) == (T0, TO + 3600)


def test_a_naive_instant_is_read_as_utc() -> None:
    assert period("2026-11-01T06:30:00", "2026-11-02", NOW).from_ == T0 + 6.5 * 3600


def test_no_range_is_the_30_days_up_to_now() -> None:
    got = period(None, None, NOW)
    assert (got.from_, got.to) == (NOW - 30 * DAY, NOW)


def test_only_from_runs_up_to_now() -> None:
    assert period("2026-11-01", None, NOW).to == NOW


def test_only_to_reaches_30_days_back() -> None:
    assert period(None, "2026-11-08", NOW).from_ == TO - 30 * DAY


@pytest.mark.parametrize(
    ("end", "ok"),
    [("2027-11-02", True), ("2027-11-03", False)],  # 366 and 367 days after Nov 1 2026
)
def test_366_days_are_accepted_and_367_refused(end: str, ok: bool) -> None:
    if ok:
        assert period("2026-11-01", end, NOW).to - T0 == 366 * DAY
    else:
        with pytest.raises(BadRequestError, match=r"^a range is at most 366 days$"):
            period("2026-11-01", end, NOW)


@pytest.mark.parametrize(
    ("start", "end"), [("2026-11-08", "2026-11-01"), ("2026-11-01", "2026-11-01")]
)
def test_an_empty_or_reversed_range_is_refused(start: str, end: str) -> None:
    with pytest.raises(BadRequestError, match=r"^from must be before to$"):
        period(start, end, NOW)


@pytest.mark.parametrize(
    "bad", ["", "yesterday", "2026-13-01", "nan", "inf", "1e9", "-5", "99999999999999999999"]
)
def test_a_value_that_is_no_date_or_time_is_refused_naming_the_parameter(bad: str) -> None:
    with pytest.raises(BadRequestError, match=r"^from is not a date or a time$"):
        period(bad, "2026-11-08", NOW)
    with pytest.raises(BadRequestError, match=r"^to is not a date or a time$"):
        period("2026-11-01", bad, NOW)


@pytest.mark.parametrize("bad", ["2026-11-01+02:00", "2026-11-01x02:00", "2026-11-01_02:00:00Z"])
def test_a_date_time_with_another_separator_than_t_or_space_is_refused(bad: str) -> None:
    with pytest.raises(BadRequestError, match=r"^from is not a date or a time$"):
        period(bad, "2026-11-08", NOW)


@pytest.mark.parametrize(
    "text", ["2026-11-01T02:00:00Z", "2026-11-01t02:00:00z", "2026-11-01 02:00:00Z"]
)
def test_a_date_time_separated_by_t_or_space_is_accepted(text: str) -> None:
    assert period(text, "2026-11-08", NOW).from_ == T0 + 2 * 3600
