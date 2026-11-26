"""The agent runs of a window, grouped by agent, model and connection."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from code_factory.metrics.models import AgentRuns, Ending, RunFacts

DEFAULT_AGENT = "the default agent"
STOPPED = -15  # SIGTERM: a run the board stopped


def ending_words(halted: str, exit_code: int) -> str:
    """How a run that did not finish ended, in the words the Flow page counts by."""
    if not halted:
        return "stopped, no reason recorded" if exit_code == STOPPED else f"exit {exit_code}"
    if halted.startswith("stopped at its cap:"):
        return "token cap" if halted.endswith(" tokens") else "time cap"
    if halted.startswith("read enough: stopped at "):
        calls = halted.removeprefix("read enough: stopped at ").split(" ", 1)[0]
        if halted.endswith("with no change in its worktree"):
            return f"no change after {calls} tool calls"
        return "one call repeated"
    return halted.split(":", 1)[0]


@dataclass
class _Row:
    runs: int = 0
    finished: int = 0
    failed: int = 0
    stopped: int = 0
    running: int = 0
    endings: Counter[str] = field(default_factory=Counter)
    tokens: int | None = None
    cost: float | None = None
    estimated: bool = False


def _count(row: _Row, run: RunFacts) -> None:
    row.runs += 1
    if run.exit_code is None:
        row.running += 1
    elif run.exit_code == 0:
        row.finished += 1
    else:
        if run.halted or run.exit_code == STOPPED:
            row.stopped += 1
        else:
            row.failed += 1
        row.endings[ending_words(run.halted, run.exit_code)] += 1
    if run.tokens is not None:
        row.tokens = (row.tokens or 0) + run.tokens
    if run.cost is not None:
        row.cost = (row.cost or 0.0) + run.cost
        row.estimated = row.estimated or run.cost_estimated


def agent_rows(runs: Sequence[RunFacts], since: float) -> list[AgentRuns]:
    """The runs started at or after `since`, by (agent, model, connection).

    Rows are ordered by runs, most first, then by key. Endings are the most frequent first, ties
    by reason. `tokens` and `cost` are None while no run reported one; `estimated` is True only
    when a counted cost is the board's estimate.
    """
    rows: dict[tuple[str, str, str], _Row] = {}
    for run in runs:
        if run.started_at.timestamp() >= since:
            key = (run.agent or DEFAULT_AGENT, run.model, run.connection)
            _count(rows.setdefault(key, _Row()), run)
    ordered = sorted(rows.items(), key=lambda item: (-item[1].runs, item[0]))
    return [
        AgentRuns(
            agent=agent,
            model=model,
            connection=connection,
            runs=row.runs,
            finished=row.finished,
            failed=row.failed,
            stopped=row.stopped,
            running=row.running,
            endings=[
                Ending(reason=reason, count=count)
                for reason, count in sorted(row.endings.items(), key=lambda e: (-e[1], e[0]))
            ],
            tokens=row.tokens,
            cost=row.cost,
            estimated=True if row.estimated else None,
        )
        for (agent, model, connection), row in ordered
    ]
