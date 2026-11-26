"""Caps and usage; sentences and numbers are the hand-worked cases of the team spec."""

import pytest

from code_factory.team.rules import over_cap, over_day_cap, usage
from team_values import DAY, MIDNIGHT, NOW, agent, ask, ended, run


def test_tokens_at_the_cap_refuse_and_one_below_passes() -> None:
    writer = agent("writer", "build", max_tokens=1000)
    at = ask(ended("r1", agent="writer", tokens=700), ended("r2", agent="writer", tokens=300))
    below = ask(ended("r1", agent="writer", tokens=700), ended("r2", agent="writer", tokens=299))
    assert over_cap(writer, at) == "writer 1,000 of 1,000 tokens"
    assert over_cap(writer, below) is None


def test_a_large_token_count_groups_its_digits_by_three() -> None:
    writer = agent("writer", "build", max_tokens=12_000_000)
    used = ask(ended("r1", agent="writer", tokens=12_345_678))
    assert over_cap(writer, used) == "writer 12,345,678 of 12,000,000 tokens"


def test_seconds_count_an_unended_run_up_to_now() -> None:
    writer = agent("writer", "build", max_seconds=600)
    at = ask(
        ended("r1", agent="writer", started=NOW - 900, seconds=400),
        run("r2", agent="writer", started=NOW - 200),
    )
    below = ask(
        ended("r1", agent="writer", started=NOW - 900, seconds=399),
        run("r2", agent="writer", started=NOW - 200),
    )
    assert over_cap(writer, at) == "writer 600 of 600 s"
    assert over_cap(writer, below) is None


def test_a_run_that_ends_before_it_starts_counts_no_negative_seconds() -> None:
    writer = agent("writer", "build", max_seconds=10)
    odd = ask(ended("r1", agent="writer", seconds=-500), ended("r2", agent="writer", seconds=9))
    assert over_cap(writer, odd) is None


def test_tokens_are_checked_before_seconds() -> None:
    writer = agent("writer", "build", max_tokens=5, max_seconds=5)
    both = ask(ended("r1", agent="writer", seconds=100, tokens=5))
    assert over_cap(writer, both) == "writer 5 of 5 tokens"


def test_only_this_agents_runs_on_this_ticket_count() -> None:
    writer = agent("writer", "build", max_tokens=10)
    other = ask(
        ended("r1", agent="coder", tokens=99),
        ended("r2", "CF-2", agent="writer", tokens=99),
        ended("r3", agent="writer", tokens=9),
    )
    assert over_cap(writer, other) is None


def test_an_agent_without_caps_is_never_over() -> None:
    assert (
        over_cap(agent("writer", "build"), ask(ended("r1", agent="writer", tokens=10**9))) is None
    )


def test_the_day_cap_reads_the_cost_of_runs_started_in_the_same_utc_day() -> None:
    writer = agent("writer", "build", max_daily_usd=1.0)
    runs = [ended("r1", agent="writer", cost=0.6), ended("r2", "CF-9", agent="writer", cost=0.4)]
    assert over_day_cap(writer, runs, NOW) == "writer $1.00 of $1.00 on 2026-11-23"


def test_the_day_boundary_is_midnight_utc() -> None:
    writer = agent("writer", "build", max_daily_usd=1.0)
    first_second = [ended("r1", agent="writer", started=MIDNIGHT, cost=1.0)]
    last_second = [ended("r1", agent="writer", started=MIDNIGHT - 1, cost=1.0)]
    next_day = [ended("r1", agent="writer", started=MIDNIGHT + DAY, cost=1.0)]
    assert over_day_cap(writer, first_second, NOW) is not None
    assert over_day_cap(writer, last_second, NOW) is None
    assert over_day_cap(writer, next_day, NOW) is None


def test_a_run_without_a_cost_adds_nothing_and_a_cost_just_below_passes() -> None:
    writer = agent("writer", "build", max_daily_usd=1.0)
    runs = [ended("r1", agent="writer", cost=0.99), ended("r2", agent="writer")]
    assert over_day_cap(writer, runs, NOW) is None


def test_the_day_cap_sentence_shows_two_decimals() -> None:
    writer = agent("writer", "build", max_daily_usd=1.5)
    assert (
        over_day_cap(writer, [ended("r1", agent="writer", cost=1.504)], NOW)
        == "writer $1.50 of $1.50 on 2026-11-23"
    )


def test_an_agent_without_a_day_cap_is_never_over_it() -> None:
    assert over_day_cap(agent("writer"), [ended("r1", agent="writer", cost=99.0)], NOW) is None


def test_the_usage_of_a_claim_run_reports_no_tokens_until_claude_ends() -> None:
    claude = agent("c", "build", runtime="claude")
    codex = agent("x", "build", runtime="codex")
    running_claude = ask(run("r1", agent="c", started=NOW - 90.9))
    running_codex = ask(run("r1", agent="x", started=NOW - 90.9))
    assert (usage(claude, running_claude).tokens, usage(claude, running_claude).seconds) == (
        None,
        90,
    )
    assert (usage(codex, running_codex).tokens, usage(codex, running_codex).seconds) == (0, 90)


def test_claude_reports_tokens_once_a_run_reported_some_or_all_ended() -> None:
    claude = agent("c", "build", runtime="claude")
    reported = ask(run("r1", agent="c", tokens=7))
    finished = ask(ended("r1", agent="c", tokens=11, seconds=30))
    assert usage(claude, reported).tokens == 7
    assert (usage(claude, finished).tokens, usage(claude, finished).seconds) == (11, 30)


@pytest.mark.parametrize("cap", [0])
def test_a_cap_of_zero_refuses_at_once(cap: int) -> None:
    assert over_cap(agent("w", "build", max_tokens=cap), ask()) == "w 0 of 0 tokens"
