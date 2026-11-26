"""What an agent's runs on a ticket and on a day add up to, and the caps they are held to."""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import NamedTuple

from code_factory.team.models import Ask, TeamAgent, TeamRun, Usage

# Runtimes that report a run's tokens only when it ends.
TOKENS_AT_END = ("claude",)


class _Spent(NamedTuple):
    tokens: int
    seconds: float


def utc_day(moment: float) -> str:
    """The UTC day of an epoch second, `2026-11-23`."""
    return datetime.fromtimestamp(moment, UTC).date().isoformat()


def mine(agent: TeamAgent, ask: Ask) -> list[TeamRun]:
    """The agent's runs on the ask's ticket."""
    return [run for run in ask.runs if run.agent == agent.name and run.ticket_id == ask.key]


def _spent(runs: Iterable[TeamRun], now: float) -> _Spent:
    tokens = 0
    seconds = 0.0
    for run in runs:
        tokens += run.tokens or 0
        seconds += max((now if run.ended_at is None else run.ended_at) - run.started_at, 0.0)
    return _Spent(tokens, seconds)


def over_cap(agent: TeamAgent, ask: Ask) -> str | None:
    """The cap the agent reached with its runs on the ticket, tokens first; `None` within both."""
    spent = _spent(mine(agent, ask), ask.now)
    if agent.max_tokens is not None and spent.tokens >= agent.max_tokens:
        return f"{agent.name} {spent.tokens:,} of {agent.max_tokens:,} tokens"
    if agent.max_seconds is not None and spent.seconds >= agent.max_seconds:
        return f"{agent.name} {int(spent.seconds)} of {agent.max_seconds} s"
    return None


def over_day_cap(agent: TeamAgent, runs: Sequence[TeamRun], now: float) -> str | None:
    """The daily cost cap reached by the agent's runs started in the UTC day of `now`."""
    if agent.max_daily_usd is None:
        return None
    day = utc_day(now)
    spent = sum(
        run.cost or 0.0
        for run in runs
        if run.agent == agent.name and utc_day(run.started_at) == day
    )
    if spent < agent.max_daily_usd:
        return None
    return f"{agent.name} ${spent:.2f} of ${agent.max_daily_usd:.2f} on {day}"


def at_cap(agent: TeamAgent, ask: Ask) -> str | None:
    """The cap that keeps the agent from a run on the ticket: its ticket's, else its day's."""
    return over_cap(agent, ask) or over_day_cap(agent, ask.runs, ask.now)


def usage(agent: TeamAgent, ask: Ask) -> Usage:
    """The tokens and whole seconds of the agent's runs on the ticket.

    Tokens are `None` while a run is active, has reported none, and the runtime reports tokens
    only at the end.
    """
    runs = mine(agent, ask)
    spent = _spent(runs, ask.now)
    later = agent.runtime in TOKENS_AT_END and any(
        run.active and run.tokens is None for run in runs
    )
    return Usage(tokens=None if later else spent.tokens, seconds=int(spent.seconds))
