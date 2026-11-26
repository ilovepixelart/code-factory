"""F4 cohort and F7 autonomy, expected values from fixture F1 (spec section 4.4)."""

from factory_values import (
    DAY,
    FROM,
    MERGED_R1,
    NOW,
    OPENED_R1,
    P1,
    P2,
    P3,
    P7,
    TO,
    nov,
    pull,
)

from code_factory.factory.models import AutonomyClass, PrCounts, PullState
from code_factory.factory.rules.cohort import autonomy, cohort


def test_the_cohort_of_the_first_week_counts_as_the_spec_works_it_out() -> None:
    got = cohort(OPENED_R1, MERGED_R1, FROM, TO, NOW)
    assert got.counts == PrCounts(opened=7, merged=4, merged_in_period=3, open=2, closed=1)


def test_the_cohort_keeps_its_members_in_the_order_given() -> None:
    got = cohort(OPENED_R1, MERGED_R1, FROM, TO, NOW)
    assert [p.number for p in got.members] == [11, 12, 13, 14, 15, 16, 17]


def test_a_repeated_url_keeps_its_first_place_in_the_order_given() -> None:
    got = cohort([P2, P1, P2], [], FROM, TO, NOW)
    assert [p.number for p in got.members] == [12, 11]


def test_a_repeated_url_keeps_its_first_record() -> None:
    renamed = P2.model_copy(update={"title": "A later record"})
    got = cohort([P2, renamed], [], FROM, TO, NOW)
    assert [p.title for p in got.members] == ["Split the loader"]


def test_a_pull_request_opened_exactly_at_from_is_in_and_at_to_is_out() -> None:
    at_from = pull(1, None, FROM)
    at_to = pull(2, None, TO)
    just_before = pull(3, None, FROM - 1)
    got = cohort([at_from, at_to, just_before], [], FROM, TO, NOW)
    assert [p.number for p in got.members] == [1]


def test_a_merge_after_the_range_still_counts_as_merged() -> None:
    got = cohort([P3], [], FROM, TO, NOW)  # P3 merges on Nov 9, after Nov 8
    assert (got.counts.merged, got.counts.merged_in_period) == (1, 0)


def test_a_merge_after_now_counts_as_open() -> None:
    future = pull(1, None, nov(2), merged=NOW + DAY)
    got = cohort([future], [], FROM, TO, NOW)
    assert (got.counts.merged, got.counts.open) == (0, 1)


def test_a_closed_pull_request_that_never_merged_counts_closed() -> None:
    closed = pull(1, None, nov(2), state=PullState.CLOSED)
    assert cohort([closed], [], FROM, TO, NOW).counts.closed == 1


def test_the_same_url_is_counted_once() -> None:
    got = cohort([P1, P1, P2], [P1, P1], FROM, TO, NOW)
    assert (got.counts.opened, got.counts.merged, got.counts.merged_in_period) == (2, 2, 1)


def test_merges_in_the_range_can_exceed_the_pull_requests_opened_in_it() -> None:
    got = cohort([], [P3], nov(8), nov(15), nov(15))  # R2: P3 merged Nov 9 12:00
    assert got.counts == PrCounts(opened=0, merged=0, merged_in_period=1, open=0, closed=0)


def test_a_merge_outside_the_range_is_not_a_merge_in_period() -> None:
    assert cohort([], [P1], nov(8), nov(15), nov(15)).counts.merged_in_period == 0


def test_an_empty_range_counts_nothing() -> None:
    assert cohort([], [], FROM, TO, NOW).counts == PrCounts(
        opened=0, merged=0, merged_in_period=0, open=0, closed=0
    )


def test_autonomy_of_the_merged_cohort_is_two_of_three() -> None:
    got = autonomy([P1, P2, P3, P7])
    assert (got.autonomous, got.assisted, got.unknown, got.share) == (2, 1, 1, 0.6666666666666666)


def test_all_unknown_has_no_share() -> None:
    assert autonomy([P7, P7]).share is None


def test_nothing_merged_has_no_share() -> None:
    assert autonomy([]).share is None


def test_unknown_is_never_in_the_denominator() -> None:
    mixed = [
        pull(1, None, FROM, merged=nov(2), autonomy=AutonomyClass.AUTONOMOUS),
        P7,
        P7,
        P7,
    ]
    assert autonomy(mixed).share == 1.0
