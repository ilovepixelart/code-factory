"""F5 pr_cost, F6 cost_summary and F12 expensive, expected values from fixture F1."""

import pytest
from factory_values import (
    COSTS,
    DAY,
    NOW,
    OPENED_R1,
    P1,
    P2,
    P3,
    P4,
    P5,
    P6,
    P7,
    RUNS,
    nov,
    pull,
    run,
)

from code_factory.factory.models import Component, PrCost, PullFact, PullState, RunCost, Size
from code_factory.factory.rules.cost import (
    cost_summary,
    expensive,
    measurement_spend,
    pr_cost,
)


def costed(pr: PullFact, costs: dict[str, RunCost] | None = None, now: float = NOW) -> PrCost:
    return pr_cost(pr, RUNS, COSTS if costs is None else costs, now)


def all_costed() -> list[PrCost]:
    return [costed(p) for p in OPENED_R1]


@pytest.mark.parametrize(
    ("pr", "cost", "runs"),
    [(P1, 1.5, 2), (P2, 5.0, 3), (P3, 2.0, 1), (P4, 10.0, 2), (P6, 1.5, 2), (P7, 1.5, 2)],
)
def test_a_pull_request_costs_its_tickets_runs_split_over_its_pull_requests(
    pr: PullFact, cost: float, runs: int
) -> None:
    got = costed(pr)
    assert (got.cost, got.complete, got.estimated, got.runs) == (cost, True, False, runs)


def test_a_ticket_with_no_priced_run_has_no_cost_and_is_incomplete() -> None:
    got = costed(P5)
    assert (got.cost, got.complete, got.runs, got.by_component) == (None, False, 1, {})


def test_a_ticket_with_a_sibling_pull_request_gives_each_the_same_share() -> None:
    assert costed(P6).cost == costed(P7).cost == 1.5


def test_the_sibling_in_another_range_gets_the_same_share() -> None:
    elsewhere = pull(99, "CF-6", nov(40), pulls=2)
    assert costed(elsewhere, now=nov(41)).cost == 1.5


def test_the_cost_is_split_by_component_after_the_same_division() -> None:
    assert costed(P7).by_component == {Component.BUILD: 1.0, Component.REVIEW: 0.5}
    assert costed(P2).by_component == {
        Component.SPEC: 0.5,
        Component.BUILD: 3.0,
        Component.REVIEW: 1.5,
    }


def test_split_and_coordinate_and_improve_runs_count_as_other() -> None:
    runs = [
        run("a", "CF-9", "split", "s", "m", "finished", nov(2)),
        run("b", "CF-9", "improve", "s", "m", "finished", nov(2)),
        run("c", "CF-9", "coordinate", "s", "m", "finished", nov(2)),
    ]
    costs = {k: RunCost(cost=1.0) for k in "abc"}
    got = pr_cost(pull(1, "CF-9", nov(3)), runs, costs, NOW)
    assert got.by_component == {Component.OTHER: 3.0}


def test_a_run_that_cost_nothing_is_priced() -> None:
    costs = {**COSTS, "r01": RunCost(cost=0.0), "r02": RunCost(cost=0.0)}
    got = costed(P1, costs)
    assert (got.cost, got.complete) == (0.0, True)


def test_a_partly_priced_ticket_sums_what_is_priced_and_says_it_is_incomplete() -> None:
    costs = {**COSTS, "r02": RunCost(cost=None)}
    got = costed(P1, costs)
    assert (got.cost, got.complete) == (1.0, False)


def test_a_run_with_no_cost_record_is_unpriced() -> None:
    costs = {k: v for k, v in COSTS.items() if k != "r02"}
    got = costed(P1, costs)
    assert (got.cost, got.complete) == (1.0, False)


def test_a_run_started_after_the_merge_is_left_out_and_one_at_the_merge_too() -> None:
    merge = nov(2, 14)  # P1 merged Nov 2 14:00
    late = run("late", "CF-1", "build", "b", "m", "finished", merge + 1)
    at_merge = run("edge", "CF-1", "build", "b", "m", "finished", merge)
    costs = {**COSTS, "late": RunCost(cost=100.0), "edge": RunCost(cost=100.0)}
    got = pr_cost(P1, [*RUNS, late, at_merge], costs, NOW)
    assert (got.cost, got.runs) == (1.5, 2)


def test_an_open_pull_request_counts_runs_up_to_now() -> None:
    after = run("later", "CF-4", "build", "b", "m", "finished", NOW + 1)
    costs = {**COSTS, "later": RunCost(cost=100.0)}
    assert pr_cost(P4, [*RUNS, after], costs, NOW).cost == 10.0


def test_a_pull_request_with_no_ticket_has_no_cost() -> None:
    got = costed(pull(1, None, nov(2)))
    assert (got.cost, got.runs) == (None, 0)


def test_an_estimated_cost_makes_the_pull_request_estimated() -> None:
    costs = {**COSTS, "r01": RunCost(cost=1.0, estimated=True)}
    assert costed(P1, costs).estimated is True


def test_an_estimated_run_outside_the_scope_does_not() -> None:
    late = run("late", "CF-1", "build", "b", "m", "finished", nov(2, 14) + 1)
    costs = {**COSTS, "late": RunCost(cost=1.0, estimated=True)}
    assert pr_cost(P1, [*RUNS, late], costs, NOW).estimated is False


def test_a_measurement_run_of_the_ticket_is_in_no_pull_request_cost() -> None:
    judged = run("jt", "CF-1", "judge", "judge", "m", "finished", nov(2, 12), source="judge")
    costs = {**COSTS, "jt": RunCost(cost=50.0)}
    got = pr_cost(P1, [*RUNS, judged], costs, NOW)
    assert (got.cost, got.runs, got.complete) == (1.5, 2, True)


def test_a_merge_stamped_after_now_is_listed_open() -> None:
    future = pull(1, "CF-1", nov(2, 10), merged=NOW + DAY)
    (top,) = expensive([costed(future)], 1)
    assert top.state == PullState.OPEN


@pytest.mark.parametrize("count", [0, -3])
def test_a_ticket_pull_count_below_one_is_read_as_one(count: int) -> None:
    assert costed(pull(1, "CF-1", nov(2, 10), merged=nov(2, 14), pulls=count)).cost == 1.5


def test_the_summary_of_the_fixture_is_the_hand_worked_figures() -> None:
    got = cost_summary(all_costed(), 0.5)
    assert (got.median, got.priced, got.of, got.estimated, got.measurement) == (
        1.75,
        6,
        7,
        False,
        0.5,
    )


def test_the_summary_median_is_not_the_mean() -> None:
    assert cost_summary(all_costed(), 0).median != pytest.approx(21.5 / 6)


def test_the_summary_by_size_is_always_four_rows_with_priced_of_counts() -> None:
    got = cost_summary(all_costed(), 0)
    assert [(s.size, s.median, s.priced, s.of) for s in got.by_size] == [
        (Size.S, 1.5, 2, 2),
        (Size.M, 3.5, 2, 2),
        (Size.L, 1.5, 1, 2),
        (Size.XL, 10.0, 1, 1),
    ]


def test_the_summary_by_component_has_medians_per_priced_pull_request_and_totals() -> None:
    got = cost_summary(all_costed(), 0)
    assert [(c.component, c.median, c.total) for c in got.by_component] == [
        (Component.SPEC, 0.0, 0.5),
        (Component.BUILD, 1.5, 16.0),
        (Component.REVIEW, 0.5, 5.0),
        (Component.OTHER, 0.0, 0.0),
    ]


def test_an_unknown_size_row_appears_only_when_a_pull_request_has_no_size() -> None:
    assert Size.UNKNOWN not in [s.size for s in cost_summary(all_costed(), 0).by_size]
    unknown = costed(pull(50, "CF-1", nov(2, 10), merged=nov(2, 14)))
    row = cost_summary([unknown], 0).by_size[-1]
    assert (row.size, row.median, row.priced, row.of) == (Size.UNKNOWN, 1.5, 1, 1)


def test_an_unpriced_pull_request_of_unknown_size_still_adds_the_row() -> None:
    row = cost_summary([costed(pull(50, "CF-5", nov(6, 9)))], 0).by_size[-1]
    assert (row.size, row.median, row.priced, row.of) == (Size.UNKNOWN, None, 0, 1)


def test_the_summary_is_estimated_when_a_priced_pull_request_is() -> None:
    costs = {**COSTS, "r01": RunCost(cost=1.0, estimated=True)}
    assert cost_summary([costed(P1, costs), costed(P2)], 0).estimated is True


def test_an_empty_cohort_has_no_median_and_zero_totals() -> None:
    got = cost_summary([], 0.0)
    assert (got.median, got.priced, got.of, got.estimated) == (None, 0, 0, False)
    assert [(c.median, c.total) for c in got.by_component] == [(None, 0.0)] * 4
    assert [(s.median, s.priced, s.of) for s in got.by_size] == [(None, 0, 0)] * 4


def test_measurement_spend_is_the_judge_and_eval_runs_not_the_board_ones() -> None:
    assert measurement_spend(RUNS, COSTS) == 0.5


def test_measurement_spend_ignores_unpriced_runs() -> None:
    assert measurement_spend(RUNS, {"j01": RunCost(cost=None), "e01": RunCost(cost=0.4)}) == 0.4


def test_the_three_most_expensive_are_14_12_13() -> None:
    got = expensive(all_costed(), 3)
    assert [p.number for p in got] == [14, 12, 13]


def test_the_first_expensive_pull_request_carries_every_field_of_the_spec_example() -> None:
    top = expensive(all_costed(), 1)[0]
    assert top.model_dump(mode="json") == {
        "url": "https://github.com/sample/sample/pull/14",
        "repository": "sample",
        "number": 14,
        "ticket": "CF-4",
        "title": "Cache the index",
        "state": "open",
        "opened_at": 1793952000.0,
        "cost": 10.0,
        "cost_complete": True,
        "estimated": False,
        "changed_lines": 1000,
        "size": "XL",
        "runs": 2,
    }


def test_equal_costs_are_ordered_by_newest_opened_and_unpriced_ones_are_left_out() -> None:
    assert [p.number for p in expensive(all_costed(), 50)] == [14, 12, 13, 17, 16, 11]


def test_equal_cost_and_opening_are_ordered_by_url() -> None:
    a = costed(pull(2, "CF-1", nov(2, 10), merged=nov(2, 14)))
    b = costed(pull(1, "CF-1", nov(2, 10), merged=nov(2, 14)))
    assert [p.number for p in expensive([a, b], 10)] == [1, 2]


def test_a_pull_request_with_no_recorded_size_lists_unknown() -> None:
    only = costed(pull(1, "CF-1", nov(2, 10), merged=nov(2, 14)))
    top = expensive([only], 1)[0]
    assert (top.changed_lines, top.size) == (None, Size.UNKNOWN)
