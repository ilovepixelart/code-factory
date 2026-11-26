"""F11 runs counted by stage, state, source, model and agent."""

from collections import Counter
from collections.abc import Callable, Sequence

from code_factory.factory.models import KeyCount, RunBreakdowns, RunFact

DEFAULT_KEY = "default"


def _counted(runs: Sequence[RunFact], key: Callable[[RunFact], str]) -> list[KeyCount]:
    """Most runs first, equal counts by key."""
    seen = Counter(key(run) or DEFAULT_KEY for run in runs)
    ordered = sorted(seen.items(), key=lambda item: (-item[1], item[0]))
    return [KeyCount(key=name, runs=count) for name, count in ordered]


def run_breakdowns(runs: Sequence[RunFact], since: float, until: float) -> RunBreakdowns:
    """The runs started in `[since, until)` counted five ways; an empty model reads `default`."""
    inside = [run for run in runs if since <= run.started_at < until]
    return RunBreakdowns(
        total=len(inside),
        by_stage=_counted(inside, lambda r: r.stage),
        by_state=_counted(inside, lambda r: r.state),
        by_source=_counted(inside, lambda r: r.source),
        by_model=_counted(inside, lambda r: r.model),
        by_agent=_counted(inside, lambda r: r.agent),
    )
