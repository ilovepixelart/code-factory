"""What a run costs: the log's own words, an estimate from its tokens at the agent's price, and
the budgets that stop it. Dollars are worked by hand."""

import math

import pytest

from code_factory.agents.models.usage import Price
from code_factory.agents.rules.logs import (
    log_cache_reads,
    log_cost,
    log_model,
    log_tokens,
    log_turns,
)
from code_factory.agents.rules.spending import (
    agent_price,
    costs_so_far,
    estimate,
    monthly_budget,
    spent_parts,
    ticket_budget,
)

RESULT = (
    '{"type":"result","total_cost_usd":0.12,"num_turns":7,'
    '"usage":{"input_tokens":10,"output_tokens":5,"cache_read_input_tokens":99},'
    '"modelUsage":{"a":{"costUSD":0.02},"b":{"costUSD":0.1}}}'
)


def test_a_result_record_gives_the_cost_model_tokens_cache_reads_and_turns() -> None:
    lines = ["not json", RESULT]
    assert log_cost(lines) == 0.12
    assert log_model(lines) == "b"
    assert log_tokens(lines) == 15
    assert log_cache_reads(lines) == 99
    assert log_turns(lines) == 7


def test_a_log_without_a_result_record_gives_none_for_each_never_zero() -> None:
    for lines in ([], ["plain"], ['{"type":"assistant"}']):
        assert log_cost(lines) is None
        assert log_model(lines) is None
        assert log_tokens(lines) is None
        assert log_cache_reads(lines) is None
        assert log_turns(lines) is None


@pytest.mark.parametrize("bad", ["-1", '"7"', "true", "1.5", "null"])
def test_a_count_that_is_not_a_whole_number_of_zero_or_more_is_none(bad: str) -> None:
    record = f'{{"type":"result","num_turns":{bad},"usage":{{"cache_read_input_tokens":{bad}}}}}'
    assert log_turns([record]) is None
    assert log_cache_reads([record]) is None


def test_zero_cache_reads_and_zero_turns_are_zero_not_none() -> None:
    record = '{"type":"result","num_turns":0,"usage":{"cache_read_input_tokens":0}}'
    assert log_turns([record]) == 0
    assert log_cache_reads([record]) == 0


def test_a_run_costs_its_tokens_at_dollars_per_million() -> None:
    price = Price(input=3.0, output=15.0)
    assert estimate(price, (1000, 500)) == pytest.approx(0.0105)
    assert estimate(price, (1_000_000, 2_000_000)) == pytest.approx(33.0)
    assert estimate(price, (0, 0)) == 0.0


def test_the_agents_price_is_both_prices_else_nothing_and_a_local_model_is_free() -> None:
    assert agent_price(3.0, 15.0, local=False) == Price(input=3.0, output=15.0)
    assert agent_price(0.0, 0.0, local=False) == Price(input=0.0, output=0.0)
    assert agent_price(None, None, local=False) is None
    assert agent_price(3.0, None, local=False) is None
    assert agent_price(None, None, local=True) == Price(input=0.0, output=0.0)
    assert agent_price(3.0, 15.0, local=True) == Price(input=3.0, output=15.0)
    for bad in (-1.0, math.inf, math.nan):
        assert agent_price(bad, 1.0, local=False) is None
        assert agent_price(bad, 1.0, local=True) == Price(input=0.0, output=0.0)


def test_the_larger_of_the_logged_and_the_reported_tokens_is_spent_and_the_log_wins_a_tie() -> None:
    assert spent_parts((10, 5), (900, 100)) == (900, 100)
    assert spent_parts((10, 5), (4, 1)) == (10, 5)
    assert spent_parts((10, 5), (5, 10)) == (10, 5)
    assert spent_parts(None, (4, 1)) == (4, 1)
    assert spent_parts((10, 5), None) == (10, 5)
    assert spent_parts(None, None) is None


def test_a_run_so_far_costs_what_its_tokens_cost_and_none_without_a_price_or_tokens() -> None:
    price = Price(input=3.0, output=15.0)
    spent = {"r1": (1000, 500), "r2": None, "r3": (0, 0)}
    got = costs_so_far(spent, price)
    assert got["r1"] == pytest.approx(0.0105)
    assert got["r2"] is None
    assert got["r3"] == 0.0
    assert costs_so_far(spent, None) == {"r1": None, "r2": None, "r3": None}
    assert costs_so_far({}, price) == {}


def test_a_ticket_budget_is_its_own_field_else_the_configured_one_else_none() -> None:
    assert ticket_budget("2.5", 9) == 2.5
    assert ticket_budget("", 9) == 9.0
    assert ticket_budget("", None) is None
    assert ticket_budget("0", 9) == 0.0
    for own in ("x", "-1", "nan", "inf"):
        assert ticket_budget(own, 4.0) == 4.0


def test_a_budget_is_a_number_or_numeric_text_of_zero_or_more() -> None:
    assert monthly_budget(100) == 100.0
    assert monthly_budget("12.5") == 12.5
    assert monthly_budget(0) == 0.0
    for bad in (-1, "x", True, None, [1], math.inf):
        assert monthly_budget(bad) is None
