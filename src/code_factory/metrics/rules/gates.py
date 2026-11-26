"""How long each gate step takes, and the text tables the `times` command prints."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from code_factory.metrics.models import ColumnTime, StepRun, StepTime
from code_factory.metrics.rules.columns import COLUMNS
from code_factory.metrics.rules.stats import percent

_PASSED = "passed"
_FAILED = "failed"


@dataclass
class _Tally:
    runs: int = 0
    passed: int = 0
    failed: int = 0
    flaky: int = 0
    waited: int = 0
    taken: list[tuple[int, str]] = field(default_factory=list)  # seconds and ticket, newest first


def _verdict(run: StepRun, step: str) -> bool | None:
    """Whether the step passed in the run, False when it failed, None when it did not run.

    A step with seconds and no state passed: only a pass records seconds.
    """
    if step in run.states:
        return {_PASSED: True, _FAILED: False}.get(run.states[step])
    return True if step in run.seconds else None


def _steps_of(run: StepRun) -> list[str]:
    return [*run.states, *(s for s in run.seconds if s not in run.states)]


def _finish(step: str, tally: _Tally) -> StepTime:
    values = sorted(seconds for seconds, _ in tally.taken)
    slowest = None
    for seconds, ticket in tally.taken:  # newest first: a tie keeps the newest ticket
        if slowest is None or seconds > slowest[0]:
            slowest = (seconds, ticket)
    return StepTime(
        step=step,
        runs=tally.runs,
        median=values[(len(values) - 1) // 2] if values else None,
        slowest=slowest[0] if slowest else None,
        slowest_on=slowest[1] if slowest else None,
        passed=tally.passed,
        failed=tally.failed,
        flaky=tally.flaky,
        waited=tally.waited,
    )


def window_runs(runs: Sequence[StepRun], last: int) -> list[StepRun]:
    """The newest `last` runs that carry step data, newest first; slept runs are dropped."""
    kept = [r for r in runs if not r.slept and (r.seconds or r.states)]
    return sorted(kept, key=lambda r: r.at, reverse=True)[:last]


def summarize_steps(runs: Sequence[StepRun], last: int) -> list[StepTime]:
    """Each step over the newest `last` runs that carry step data (slept runs are dropped).

    The median is the lower middle of the passes' seconds, so every number is one a run took.
    Ordered by median, largest first (no pass last), then by step.
    """
    newest = window_runs(runs, last)
    tallies: dict[str, _Tally] = {}
    for run in newest:
        for step in _steps_of(run):
            passed = _verdict(run, step)
            if passed is None:
                continue
            tally = tallies.setdefault(step, _Tally())
            tally.runs += 1
            tally.passed += passed
            tally.failed += not passed
            tally.flaky += step in run.retried
            tally.waited += run.lock_waits.get(step, 0)
            if step in run.seconds:
                tally.taken.append((run.seconds[step], run.ticket_id))
    times = [_finish(step, tally) for step, tally in tallies.items()]
    return sorted(times, key=lambda t: (t.median is None, -(t.median or 0), t.step))


def steps_table(times: Sequence[StepTime]) -> str:
    """The table: a header and a line per step; the step column is four wider than its longest."""
    width = max([len(t.step) for t in times] + [len("step")]) + 4
    header = (
        f"{'step':<{width}}{'runs':>4}{'median':>8}{'slowest':>9}{'passed':>8}{'failed':>8}"
        f"{'flaky':>7}{'waited':>8}  slowest on"
    )
    lines = [header]
    for t in times:
        rates = [f"{percent(n, t.runs)}%" for n in (t.passed, t.failed, t.flaky)]
        lines.append(
            f"{t.step:<{width}}{t.runs:>4}{_cell(t.median):>8}{_cell(t.slowest):>9}"
            f"{rates[0]:>8}{rates[1]:>8}{rates[2]:>7}{t.waited:>8}  {t.slowest_on or '-'}"
        )
    return "\n".join(lines) + "\n"


def _cell(value: int | None) -> str:
    return "-" if value is None else str(value)


def columns_table(rows: Sequence[ColumnTime], since: str) -> str:
    """The minutes section: a title, a header and a line per ticket; `-` is a column not entered."""
    width = max([len(r.ticket) for r in rows] + [len("ticket")]) + 4
    lines = [
        f"minutes in each column of the tickets that moved since {since}",
        f"{'ticket':<{width}}" + "".join(f"{name:>7}" for name in COLUMNS) + "  now",
    ]
    lines.extend(
        f"{r.ticket:<{width}}" + "".join(f"{_cell(m):>7}" for m in r.minutes) + f"  {r.now}"
        for r in rows
    )
    return "\n".join(lines) + "\n"


def revert_line(merges: int, reverted: int, since: str) -> str:
    """`merges since <stamp>: <n>, reverted later: <k> (<p>%)`, the share half up."""
    share = percent(reverted, merges)
    return f"merges since {since}: {merges}, reverted later: {reverted} ({share}%)\n"
