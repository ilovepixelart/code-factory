"""Merge outcomes by the number of fixes the board recorded."""

from collections import Counter
from collections.abc import Mapping, Sequence

from code_factory.factory.models import FixRoundOutcome, PullFact, PullState
from code_factory.factory.rules.cohort import state_at


def fix_outcomes(
    pulls: Sequence[PullFact], repairs: Mapping[str, Sequence[float]], now: float
) -> list[FixRoundOutcome]:
    """Use settled PRs as the denominator and show open PRs in the same cohort."""
    groups: dict[int, Counter[PullState]] = {}
    for pull in pulls:
        if pull.ticket_id is None or pull.ticket_id not in repairs:
            continue
        state = state_at(pull, now)
        ended = pull.merged_at if state is PullState.MERGED else pull.closed_at
        until = min(ended, now) if ended is not None else now
        count = sum(at <= until for at in repairs[pull.ticket_id])
        groups.setdefault(count, Counter())[state] += 1
    output = []
    for count, states in sorted(groups.items()):
        merged = states[PullState.MERGED]
        closed = states[PullState.CLOSED]
        output.append(
            FixRoundOutcome(
                rounds=count,
                merged=merged,
                closed=closed,
                open=states[PullState.OPEN],
                merge_rate=merged / (merged + closed) if merged + closed else None,
            )
        )
    return output
