"""F4 the cohort of a range and F7 its autonomy."""

from collections import Counter
from collections.abc import Sequence

from code_factory.factory.models import (
    Autonomy,
    AutonomyClass,
    Cohort,
    PrCounts,
    PullFact,
    PullState,
)


def is_merged(pull: PullFact, now: float) -> bool:
    """Merged as far as `now` knows: a merge stamped later than `now` has not happened."""
    return pull.merged_at is not None and pull.merged_at <= now


def state_at(pull: PullFact, now: float) -> PullState:
    """Where the pull request stood at `now`: a merge stamped later has not happened yet."""
    if is_merged(pull, now):
        return PullState.MERGED
    return PullState.CLOSED if pull.state == PullState.CLOSED else PullState.OPEN


def cohort(
    pulls: Sequence[PullFact],
    merged: Sequence[PullFact],
    since: float,
    until: float,
    now: float,
) -> Cohort:
    """The pull requests first observed in `[since, until)`, one per url, with their counts.

    `merged` is what the second provider call answered: the pull requests merged in the range,
    opened in it or before; only their number in the range is used.
    """
    first: dict[str, PullFact] = {}
    for pull in pulls:
        first.setdefault(pull.url, pull)
    members = [p for p in first.values() if since <= p.opened_at < until]
    in_period = {p.url for p in merged if p.merged_at is not None and since <= p.merged_at < until}
    states = Counter(state_at(p, now) for p in members)
    done, closed = states[PullState.MERGED], states[PullState.CLOSED]
    counts = PrCounts(
        opened=len(members),
        merged=done,
        merged_in_period=len(in_period),
        open=len(members) - done - closed,
        closed=closed,
    )
    return Cohort(members=members, counts=counts)


def autonomy(merged: Sequence[PullFact]) -> Autonomy:
    """Merged pull requests by autonomy; the share ignores `unknown`, None when nothing else."""
    seen = Counter(p.autonomy for p in merged)
    autonomous, assisted = seen[AutonomyClass.AUTONOMOUS], seen[AutonomyClass.ASSISTED]
    known = autonomous + assisted
    return Autonomy(
        share=autonomous / known if known else None,
        autonomous=autonomous,
        assisted=assisted,
        unknown=seen[AutonomyClass.UNKNOWN],
    )
