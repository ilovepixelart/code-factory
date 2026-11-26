"""F8 the durations of one merged pull request and F9 their medians over a cohort."""

from collections.abc import Callable, Sequence

from code_factory.factory.models import Cycle, CycleSummary, PullFact, RunFact, Spread, StageSpread
from code_factory.factory.rules.stats import median

_STAGES: tuple[tuple[str, Callable[[Cycle], float | None]], ...] = (
    ("kickoff_to_pr", lambda c: c.kickoff_to_pr),
    ("pr_to_review", lambda c: c.pr_to_review),
    ("review_to_merge", lambda c: c.review_to_merge),
)


def kickoffs(runs: Sequence[RunFact]) -> dict[str, float]:
    """Each ticket's first run start, from the runs given."""
    first: dict[str, float] = {}
    for run in runs:
        if run.ticket_id is not None:
            first[run.ticket_id] = min(run.started_at, first.get(run.ticket_id, run.started_at))
    return first


def _span(start: float | None, end: float | None) -> float | None:
    """`end - start`; a negative span is dropped, never clamped (a bad clock lowers no median)."""
    if start is None or end is None or end < start:
        return None
    return end - start


def cycle(pull: PullFact, kickoff: float | None) -> Cycle:
    """Kickoff to pull request, to first review, to merge, and kickoff to merge.

    A kickoff after the pull request opened is no kickoff. A first review outside
    `[opened, merged]` drops both stages around it.
    """
    start = kickoff if kickoff is not None and kickoff <= pull.opened_at else None
    review = pull.first_review_at
    in_window = (
        review is not None
        and pull.merged_at is not None
        and pull.opened_at <= review <= pull.merged_at
    )
    return Cycle(
        kickoff_to_pr=_span(start, pull.opened_at),
        pr_to_review=_span(pull.opened_at, review) if in_window else None,
        review_to_merge=_span(review, pull.merged_at) if in_window else None,
        total=_span(start, pull.merged_at),
    )


def _spread(values: Sequence[float | None]) -> Spread:
    present = [v for v in values if v is not None]
    return Spread(median=median(present), count=len(present))


def cycle_summary(rows: Sequence[Cycle]) -> CycleSummary:
    """Median and count per stage and for the total, over the values that exist."""
    stages = [
        StageSpread(stage=name, **_spread([pick(row) for row in rows]).model_dump())
        for name, pick in _STAGES
    ]
    return CycleSummary(total=_spread([row.total for row in rows]), stages=stages)
