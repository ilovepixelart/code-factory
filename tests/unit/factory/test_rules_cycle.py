"""F8 cycle and F9 cycle_summary, expected values from fixture F1."""

import pytest

from code_factory.factory.models import Cycle, PullFact
from code_factory.factory.rules.cycle import cycle, cycle_summary, kickoffs
from factory_values import P1, P2, P3, P7, RUNS, nov, pull


def of(pr: PullFact) -> Cycle:
    return cycle(pr, kickoffs(RUNS).get(pr.ticket_id or ""))


@pytest.mark.parametrize(
    ("pr", "expected"),
    [
        (P1, Cycle(kickoff_to_pr=3600, pr_to_review=3600, review_to_merge=10800, total=18000)),
        (P2, Cycle(kickoff_to_pr=7200, pr_to_review=21600, review_to_merge=64800, total=93600)),
        (P3, Cycle(kickoff_to_pr=21600, pr_to_review=86400, review_to_merge=259200, total=367200)),
        (P7, Cycle(kickoff_to_pr=10800, pr_to_review=None, review_to_merge=None, total=64800)),
    ],
)
def test_the_stages_of_a_merged_pull_request(pr: PullFact, expected: Cycle) -> None:
    assert of(pr) == expected


def test_the_kickoff_of_a_ticket_is_its_earliest_run() -> None:
    assert kickoffs(RUNS)["CF-2"] == nov(3, 8)
    assert set(kickoffs(RUNS)) == {"CF-1", "CF-2", "CF-3", "CF-4", "CF-5", "CF-6"}


def test_a_review_before_the_pull_request_opened_is_dropped() -> None:
    pr = pull(1, "CF-9", nov(3, 10), merged=nov(4), review=nov(3, 9))
    got = cycle(pr, nov(3, 8))
    assert (got.pr_to_review, got.review_to_merge) == (None, None)


def test_a_review_after_the_merge_is_dropped() -> None:
    pr = pull(1, "CF-9", nov(3, 10), merged=nov(4), review=nov(4, 1))
    got = cycle(pr, nov(3, 8))
    assert (got.pr_to_review, got.review_to_merge) == (None, None)


def test_a_review_at_the_opening_and_at_the_merge_is_kept() -> None:
    pr = pull(1, "CF-9", nov(3, 10), merged=nov(4), review=nov(3, 10))
    assert cycle(pr, nov(3, 8)).pr_to_review == 0
    pr = pull(1, "CF-9", nov(3, 10), merged=nov(4), review=nov(4))
    assert cycle(pr, nov(3, 8)).review_to_merge == 0


def test_a_kickoff_after_the_opening_is_dropped() -> None:
    got = cycle(P1, P1.opened_at + 1)
    assert (got.kickoff_to_pr, got.total) == (None, None)


def test_a_kickoff_at_the_opening_is_zero() -> None:
    assert cycle(P1, P1.opened_at).kickoff_to_pr == 0


def test_a_merge_before_the_kickoff_is_dropped_not_clamped_to_zero() -> None:
    pr = pull(1, "CF-9", nov(3, 10), merged=nov(3, 7))
    got = cycle(pr, nov(3, 8))
    assert got.total is None


def test_a_ticket_with_no_runs_has_no_kickoff_stages_but_keeps_the_review_ones() -> None:
    got = cycle(P1, None)
    assert (got.kickoff_to_pr, got.total, got.pr_to_review) == (None, None, 3600)


def test_the_summary_of_the_fixture_is_the_hand_worked_medians_and_counts() -> None:
    got = cycle_summary([of(p) for p in (P1, P2, P3, P7)])
    assert (got.total.median, got.total.count) == (79200.0, 4)
    assert [(s.stage, s.median, s.count) for s in got.stages] == [
        ("kickoff_to_pr", 9000.0, 4),
        ("pr_to_review", 21600.0, 3),
        ("review_to_merge", 64800.0, 3),
    ]


def test_stage_medians_do_not_add_up_to_the_total_median() -> None:
    got = cycle_summary([of(p) for p in (P1, P2, P3, P7)])
    assert sum(s.median or 0 for s in got.stages) == 95400
    assert got.total.median != 95400


def test_the_summary_of_nothing_has_no_median_and_no_count() -> None:
    got = cycle_summary([])
    assert (got.total.median, got.total.count) == (None, 0)
    assert [(s.median, s.count) for s in got.stages] == [(None, 0)] * 3
