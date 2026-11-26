from datetime import UTC, datetime

import pytest

from code_factory.runs.models import BudgetScope, RunCost
from code_factory.runs.rules.budget import (
    Spent,
    attempt_count,
    limit_until,
    period,
    remaining_budget,
    review_unpaid,
)


def ticket(budget: float, spent: float) -> BudgetScope:
    return BudgetScope(name="ticket", budget=budget, spent=spent)


def month(budget: float, spent: float) -> BudgetScope:
    return BudgetScope(name="month", budget=budget, spent=spent, month="2026-11")


def test_a_reset_a_minute_ahead_waits_for_the_floor_after_the_end() -> None:
    assert limit_until(160.0, 100.0, 3600) == 400.0


def test_a_stated_reset_beyond_the_floor_is_kept() -> None:
    assert limit_until(10_000.0, 100.0, 3600) == 10_000.0


def test_no_stated_reset_waits_the_configured_time_after_the_end() -> None:
    assert limit_until(None, 100.0, 3600) == 3700.0
    assert limit_until(None, 100.0, 60) == 400.0


def test_a_period_is_a_utc_day_or_month() -> None:
    moment = datetime(2026, 11, 30, 23, 59, 59, tzinfo=UTC)
    assert period("day", moment) == "2026-11-30"
    assert period("month", moment) == "2026-11"


def test_no_scope_leaves_a_run_uncapped() -> None:
    assert remaining_budget([], 0, 1) is None


def test_the_smaller_remainder_of_the_scopes_caps_a_run() -> None:
    assert remaining_budget([ticket(10, 4), month(5, 4.5)], 0, 1) == pytest.approx(0.5)


def test_an_attempt_shares_the_remainder_among_the_attempts() -> None:
    assert remaining_budget([ticket(10, 4), month(5, 4.5)], 2, 3) == pytest.approx(0.5 / 3)


def test_a_spent_ticket_budget_refuses_with_both_amounts() -> None:
    refused = remaining_budget([ticket(4, 4.5)], 0, 1)
    assert refused == Spent(
        scope="ticket", spent=4.5, budget=4, note="budget reached ($4.50 of $4.00)"
    )


def test_a_budget_spent_exactly_refuses() -> None:
    assert isinstance(remaining_budget([ticket(4, 4)], 0, 1), Spent)


def test_a_spent_month_refuses_with_its_own_sentence() -> None:
    refused = remaining_budget([ticket(10, 1), month(4, 4)], 0, 1)
    assert isinstance(refused, Spent)
    assert refused.note == "the repository's budget for 2026-11 is reached ($4.00 of $4.00)"


def test_the_first_spent_scope_in_order_is_the_one_named() -> None:
    refused = remaining_budget([ticket(1, 2), month(1, 2)], 0, 1)
    assert isinstance(refused, Spent)
    assert refused.scope == "ticket"


def test_a_review_is_unpaid_when_a_budget_is_spent() -> None:
    unpaid = review_unpaid([ticket(4, 5)], [])
    assert unpaid is not None
    assert unpaid.note == "budget reached ($5.00 of $4.00)"


def test_a_review_is_unpaid_when_a_priced_ended_run_recorded_no_cost() -> None:
    runs = [RunCost(id="ab12", priced=True)]
    unpaid = review_unpaid([ticket(10, 1)], runs)
    assert unpaid is not None
    assert unpaid.note == "the ticket's budget ($10.00) cannot be judged: run ab12 recorded no cost"


def test_the_month_names_its_month_when_its_cost_is_unknown() -> None:
    runs = [RunCost(id="cd34", priced=True)]
    unpaid = review_unpaid([month(10, 1)], runs)
    assert unpaid is not None
    assert unpaid.note == (
        "the repository's budget for 2026-11 ($10.00) cannot be judged: run cd34 recorded no cost"
    )


@pytest.mark.parametrize(
    "run",
    [
        RunCost(id="a", priced=False),
        RunCost(id="b", priced=True, cost=0.0),
        RunCost(id="c", priced=True, ended=False),
    ],
)
def test_a_run_that_is_free_costed_or_still_running_does_not_make_a_review_unpaid(
    run: RunCost,
) -> None:
    assert review_unpaid([ticket(10, 1)], [run]) is None


@pytest.mark.parametrize(
    ("parallel", "configured", "count"),
    [
        ("3", None, 3),
        ("4", None, 4),
        ("1", 4, 1),
        (" 2 ", 5, 2),
        ("5", 3, 3),
        ("0", 3, 3),
        ("", 2, 2),
        ("", 5, 5),
        ("", 6, 1),
        ("", 1, 1),
        ("", None, 1),
        ("many", None, 1),
    ],
)
def test_the_tickets_own_parallel_sets_the_attempts_then_the_agents_setting_then_one(
    parallel: str, configured: int | None, count: int
) -> None:
    assert attempt_count(parallel, configured) == count
