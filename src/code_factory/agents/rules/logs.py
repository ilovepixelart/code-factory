"""Readers of a run's log: claude's `result` record and codex's completed turns."""

import json
from collections.abc import Sequence
from typing import Any

from code_factory.agents.models.usage import LogUsage


def records(lines: Sequence[str]) -> list[dict[str, Any]]:
    """The JSON objects of a log, one per line; the other lines are skipped."""
    found: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            found.append(value)
    return found


def amount(value: object) -> float | None:
    """A dollar amount a record states: a number or a numeric text, 0 or more, finite."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if isinstance(value, int | float) and 0 <= value < float("inf"):
        return float(value)
    return None


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _result(found: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((r for r in reversed(found) if r.get("type") == "result"), None)


def _codex_turns(found: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Each completed codex turn's input less its cached part, and its output."""
    turns: list[tuple[int, int]] = []
    for record in found:
        usage = record.get("usage")
        if record.get("type") != "turn.completed" or not isinstance(usage, dict):
            continue
        cached = _count(usage.get("cached_input_tokens")) or 0
        turns.append(
            (
                max((_count(usage.get("input_tokens")) or 0) - cached, 0),
                _count(usage.get("output_tokens")) or 0,
            )
        )
    return turns


def _model(result: dict[str, Any]) -> str | None:
    """The model that cost the most in a run, from its result record's model usage."""
    usage = result.get("modelUsage")
    if not isinstance(usage, dict):
        return None
    top: tuple[str, float] | None = None
    for name, entry in usage.items():
        cost = (amount(entry.get("costUSD")) if isinstance(entry, dict) else None) or 0.0
        if top is None or cost > top[1]:
            top = (str(name), cost)
    return None if top is None else top[0]


def log_usage(lines: Sequence[str]) -> LogUsage:
    """What a claude or codex run's log reports: cost, input and output tokens, model."""
    found = records(lines)
    result = _result(found)
    if result is not None:
        usage = result.get("usage")
        counts = usage if isinstance(usage, dict) else {}
        return LogUsage(
            cost=amount(result.get("total_cost_usd")),
            input_tokens=_count(counts.get("input_tokens")),
            output_tokens=_count(counts.get("output_tokens")),
            model=_model(result),
        )
    turns = _codex_turns(found)
    if not turns:
        return LogUsage()
    return LogUsage(input_tokens=sum(i for i, _ in turns), output_tokens=sum(o for _, o in turns))


def spent_note(spent: float, budget: float) -> str:
    """Say that the budget is reached, with both amounts."""
    return f"budget reached (${spent:.2f} of ${budget:.2f})"


def month_spent_note(month: str, spent: float, budget: float) -> str:
    """Why a start is refused once the repository's runs in `month` spent its monthly budget."""
    return f"the repository's budget for {month} is reached (${spent:.2f} of ${budget:.2f})"


def log_cost(lines: Sequence[str]) -> float | None:
    """The cost the run's last result record states, in dollars."""
    return log_usage(lines).cost


def log_model(lines: Sequence[str]) -> str | None:
    """The model that cost the most in the run, from its result record."""
    return log_usage(lines).model


def log_tokens(lines: Sequence[str]) -> int | None:
    """The input and output tokens the log reports, cache reads left out."""
    return log_usage(lines).tokens


def _result_count(lines: Sequence[str], pick: str, *, in_usage: bool) -> int | None:
    result = _result(records(lines))
    if result is None:
        return None
    holder = result.get("usage") if in_usage else result
    return _count(holder.get(pick)) if isinstance(holder, dict) else None


def log_cache_reads(lines: Sequence[str]) -> int | None:
    """The cache read tokens claude's last result record reports."""
    return _result_count(lines, "cache_read_input_tokens", in_usage=True)


def log_turns(lines: Sequence[str]) -> int | None:
    """The turns claude's last result record reports (`num_turns`)."""
    return _result_count(lines, "num_turns", in_usage=False)
