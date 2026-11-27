"""Merge outcome cohorts use recorded fix events up to the PR's outcome."""

from code_factory.factory.models import PullFact, PullState
from code_factory.factory.rules.fixes import fix_outcomes


def _pull(number: int, state: PullState, merged_at: float | None = None) -> PullFact:
    return PullFact(
        url=f"https://example.test/pull/{number}",
        repository="sample",
        number=number,
        ticket_id=f"CF-{number}",
        title="Update",
        opened_at=20,
        state=state,
        merged_at=merged_at,
    )


def test_merged_and_closed_pulls_share_a_denominator_and_open_pulls_are_reported_separately() -> (
    None
):
    pulls = [
        _pull(1, PullState.MERGED, 30),
        _pull(2, PullState.CLOSED),
        _pull(3, PullState.OPEN),
        _pull(4, PullState.MERGED, 30),
    ]
    events = {"CF-1": [25, 31], "CF-2": [25], "CF-3": [25], "CF-4": []}

    without_repairs, after_one = fix_outcomes(pulls, events, 40)

    assert (without_repairs.rounds, without_repairs.merged, without_repairs.merge_rate) == (0, 1, 1)
    assert (after_one.rounds, after_one.merged, after_one.closed, after_one.open) == (1, 1, 1, 1)
    assert after_one.merge_rate == 0.5


def test_closed_pull_does_not_accumulate_repairs_for_its_replacement() -> None:
    pull = _pull(1, PullState.CLOSED).model_copy(update={"closed_at": 27})

    [outcome] = fix_outcomes([pull], {"CF-1": [25, 30]}, 40)

    assert (outcome.closed, outcome.rounds) == (1, 1)
