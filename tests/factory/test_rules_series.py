"""F10 series: opened versus merged per bucket, with hand-worked fixture F1 values."""

import random

from factory_values import DAY, FROM, NOW, OPENED_R1, T0, TO, nov, pull

from code_factory.factory.models import PullState
from code_factory.factory.rules.series import series

WEEK = 7 * DAY


def test_the_first_week_of_november_is_seven_daily_points() -> None:
    got = series(OPENED_R1, FROM, TO, NOW)
    assert got.bucket == "day"
    assert [(p.start, p.opened, p.merged) for p in got.points] == [
        (T0 + i * DAY, o, m)
        for i, (o, m) in enumerate([(0, 0), (1, 1), (1, 1), (0, 0), (1, 1), (2, 0), (2, 1)])
    ]


def test_31_days_are_daily_and_32_days_are_weekly() -> None:
    assert series([], FROM, FROM + 31 * DAY, NOW).bucket == "day"
    assert len(series([], FROM, FROM + 31 * DAY, NOW).points) == 31
    weekly = series([], FROM, FROM + 32 * DAY, NOW)
    assert weekly.bucket == "week"


def test_a_weekly_range_starts_its_buckets_on_mondays() -> None:
    # Nov 1 2026 is a Sunday: the first bucket is the week of Monday Oct 26.
    got = series([], FROM, FROM + 32 * DAY, NOW)
    assert [p.start for p in got.points] == [nov(-5) + i * WEEK for i in range(6)]


def test_a_range_from_monday_to_monday_of_six_weeks_has_six_points() -> None:
    got = series([], nov(2), nov(44), NOW)  # Monday Nov 2 to Monday Dec 14
    assert got.bucket == "week"
    assert [p.start for p in got.points] == [nov(2) + i * WEEK for i in range(6)]


def test_the_last_second_of_a_week_and_the_first_of_the_next_fall_in_different_buckets() -> None:
    last, first = pull(1, None, nov(9) - 1), pull(2, None, nov(9))
    got = series([last, first], nov(2), nov(44), NOW)
    assert [(p.opened) for p in got.points][:2] == [1, 1]


def test_a_weekly_range_ending_on_a_monday_has_no_point_starting_at_its_end() -> None:
    since = 4 * DAY - 7 * WEEK  # Monday 1969-11-17: 1970-01-05 was a Monday
    got = series([], since, since + 6 * WEEK, NOW)
    assert [p.start for p in got.points] == [since + i * WEEK for i in range(6)]


def test_a_bucket_cut_by_the_range_counts_only_inside_it() -> None:
    before, inside, at_end = (
        pull(1, None, nov(3)),
        pull(2, None, nov(5)),
        pull(3, None, nov(44, 12)),
    )
    got = series([before, inside, at_end], nov(4, 12), nov(44, 12), NOW)  # Wed to Tue 41 days
    assert got.bucket == "week"
    assert got.points[0].start == nov(2)
    assert got.points[-1].start == nov(44)
    assert [p.opened for p in got.points] == [1, 0, 0, 0, 0, 0, 0]


def test_a_pull_request_that_merged_after_now_is_not_merged() -> None:
    late = pull(1, None, nov(2), merged=NOW + DAY)
    assert series([late], FROM, TO, NOW).points[1].merged == 0


def test_no_pull_requests_gives_all_zero_points() -> None:
    got = series([], FROM, TO, NOW)
    assert [(p.opened, p.merged) for p in got.points] == [(0, 0)] * 7


def test_merged_never_exceeds_opened_and_sums_match_the_cohort_over_random_sets() -> None:
    rng = random.Random(1)  # noqa: S311  # seeded for a reproducible set, not security
    for _ in range(200):
        since = nov(1) + rng.randrange(0, 5) * DAY + rng.randrange(0, 24) * 3600
        until = since + rng.randrange(1, 90) * DAY
        pulls = []
        for number in range(rng.randrange(0, 30)):
            opened = since - 3 * DAY + rng.random() * (until - since + 6 * DAY)
            merged = opened + rng.random() * 20 * DAY if rng.random() < 0.6 else None
            pulls.append(pull(number, None, opened, merged=merged, state=PullState.OPEN))
        got = series(pulls, since, until, NOW)
        inside = [p for p in pulls if since <= p.opened_at < until]
        merged = [p for p in inside if p.merged_at is not None and p.merged_at <= NOW]
        assert all(p.merged <= p.opened for p in got.points)
        assert sum(p.opened for p in got.points) == len(inside)
        assert sum(p.merged for p in got.points) == len(merged)


def test_a_weekly_bucket_before_the_epoch_counts_a_pull_opened_inside_it() -> None:
    # Range Dec 1 1969 to Feb 1 1970 (weekly); the pull opened Jan 3 1970 (a Saturday) 23:05:29.39
    # sits in the week of Monday Dec 29 1969 whose start is exactly -259200.
    opened = 255929.390375
    got = series([pull(1, None, opened)], -2592000.0, 2678400.0, NOW)
    assert got.bucket == "week"
    assert [p.opened for p in got.points if p.start == -259200.0] == [1]
