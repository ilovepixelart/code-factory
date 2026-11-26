"""Stage timelines, the weeks and days tickets finish in, and the seeded forecast."""

import json
from pathlib import Path
from typing import Any, cast

import pytest

from code_factory.metrics.models import Transition
from code_factory.metrics.rules.stages import (
    daily_counts,
    forecast,
    measured_done,
    reached_done,
    stage_timeline,
    start_seen,
    throughput,
    time_in_stages,
)
from repo_files import ROOT

DAY = 86400.0
# Monday 2026-10-05 00:00:00 UTC: 20731 days after 1970-01-01.
MONDAY = 1_791_158_400.0
WEDNESDAY_NOON = MONDAY + 2.5 * DAY


def at(seconds: float, stage: str) -> Transition:
    return Transition(at=seconds, stage=stage)


def done_at(seconds: float, stage: str) -> list[Transition]:
    return [at(seconds - DAY, "spec"), at(seconds, stage)]


def test_a_timeline_starts_at_the_filing_and_follows_the_moves() -> None:
    timeline = stage_timeline(0.0, "spec", [(3600.0, "build"), (10800.0, "review")])
    assert timeline == [at(0.0, "spec"), at(3600.0, "build"), at(10800.0, "review")]


def test_a_ticket_with_no_moves_is_in_its_first_stage_from_filing() -> None:
    assert stage_timeline(5.0, "spec", []) == [at(5.0, "spec")]


def test_a_move_to_the_stage_already_current_adds_nothing() -> None:
    timeline = stage_timeline(0.0, "spec", [(10.0, "spec"), (20.0, "build"), (30.0, "build")])
    assert timeline == [at(0.0, "spec"), at(20.0, "build")]


def test_moves_sharing_one_instant_collapse_to_the_last() -> None:
    timeline = stage_timeline(0.0, "spec", [(10.0, "build"), (10.0, "review")])
    assert timeline == [at(0.0, "spec"), at(10.0, "review")]


def test_a_move_at_the_filing_instant_replaces_the_first_stage() -> None:
    assert stage_timeline(10.0, "spec", [(10.0, "build")]) == [at(10.0, "build")]


def test_time_in_stages_adds_up_a_stage_entered_twice_and_runs_the_last_to_now() -> None:
    timeline = [at(0.0, "spec"), at(20.0, "build"), at(30.0, "spec")]
    assert time_in_stages(timeline, 50.0) == [("spec", 40.0), ("build", 10.0)]


def test_time_in_stages_never_goes_negative() -> None:
    assert time_in_stages([at(100.0, "spec")], 50.0) == [("spec", 0.0)]


def test_done_is_the_first_stage_that_is_review_or_later() -> None:
    timeline = [at(1.0, "spec"), at(2.0, "build"), at(3.0, "review"), at(4.0, "merged")]
    assert reached_done(timeline) == 3.0
    assert reached_done([at(1.0, "spec"), at(2.0, "build")]) is None


def test_an_unknown_stage_sorts_after_every_stage() -> None:
    assert reached_done([at(1.0, "spec"), at(2.0, "released")]) == 2.0


def test_a_timeline_beginning_at_review_or_merged_has_no_seen_start() -> None:
    assert start_seen([at(1.0, "spec")])
    assert start_seen([at(1.0, "build")])
    assert not start_seen([at(1.0, "review")])
    assert not start_seen([at(1.0, "merged")])
    assert not start_seen([])


def test_a_done_time_is_measured_only_when_the_start_was_seen() -> None:
    assert measured_done([at(1.0, "spec"), at(9.0, "review")]) == 9.0
    assert measured_done([at(9.0, "review"), at(10.0, "merged")]) is None


def test_throughput_counts_each_ticket_in_the_utc_week_it_first_reached_review() -> None:
    timelines = [
        done_at(MONDAY, "review"),
        done_at(WEDNESDAY_NOON, "merged"),
        done_at(MONDAY - 1.0, "review"),
        done_at(MONDAY - 7.0 * DAY, "released"),
        done_at(MONDAY - 49.0 * DAY, "review"),
        done_at(MONDAY - 49.0 * DAY - 1.0, "review"),
        done_at(WEDNESDAY_NOON + 1.0, "review"),
        [at(MONDAY, "spec"), at(MONDAY + 1.0, "build")],
    ]
    assert throughput(timelines, WEDNESDAY_NOON) == [1, 0, 0, 0, 0, 0, 2, 2]


def test_throughput_of_nothing_is_eight_zeros() -> None:
    assert throughput([], WEDNESDAY_NOON) == [0] * 8


def test_daily_counts_split_at_midnight_utc() -> None:
    now = MONDAY + 10.0
    timelines = [
        done_at(MONDAY, "review"),
        done_at(MONDAY - 1.0, "review"),
        done_at(MONDAY - 55.0 * DAY, "review"),
        done_at(MONDAY - 56.0 * DAY, "review"),
    ]
    counts = daily_counts(timelines, now)
    assert len(counts) == 56
    assert counts[-1] == 1  # Monday itself
    assert counts[-2] == 1  # one second before Monday is Sunday
    assert counts[0] == 1  # 55 days back is the oldest day kept
    assert sum(counts) == 3  # 56 days back is out


def test_a_forecast_with_nothing_open_is_done_today() -> None:
    assert forecast([3], 0) == (0, 0)
    assert forecast([], 0) == (0, 0)


def test_a_forecast_with_no_positive_sample_says_nothing() -> None:
    assert forecast([], 1) is None
    assert forecast([0, 0], 1) is None


def test_the_forecast_of_a_steady_sample_is_the_open_tickets_over_the_daily_rate() -> None:
    assert forecast([1], 1) == (1, 1)
    assert forecast([2, 2], 3) == (2, 2)
    assert forecast([3], 3) == (1, 1)
    assert forecast([3], 4) == (2, 2)


def test_the_forecast_stops_at_ten_years_of_days() -> None:
    assert forecast([1], 3649) == (3649, 3649)
    assert forecast([1], 3650) == (3650, 3650)
    assert forecast([1], 3651) == (3650, 3650)


def golden_forecasts() -> list[dict[str, Any]]:
    path = ROOT / "tests" / "support" / "golden" / "formats" / "metrics" / "forecasts.golden.json"
    return cast("list[dict[str, Any]]", json.loads(Path(path).read_text(encoding="utf-8")))


@pytest.mark.parametrize("case", range(5))
def test_the_forecast_reproduces_the_golden_cases_of_the_seeded_generator(case: int) -> None:
    golden = golden_forecasts()[case]
    days = golden["days"]
    expected = None if days is None else (days["p50"], days["p85"])
    assert forecast(golden["sample"], golden["open"]) == expected
