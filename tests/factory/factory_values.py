"""Fixture F1 of the factory spec (section 4.4): the facts the hand-worked figures come from.

Every time is written as a day of November 2026 and an hour, so a figure can be checked against
the spec's tables by eye. `T0` is 2026-11-01T00:00Z.
"""

from code_factory.factory.models import (
    AutonomyClass,
    PullFact,
    PullState,
    RunCost,
    RunFact,
    ScorerCard,
)

T0 = 1793491200.0
DAY = 86400.0
HOUR = 3600.0
FROM = T0  # range R1 is [Nov 1, Nov 8)
TO = T0 + 7 * DAY
NOW = T0 + 9 * DAY  # Nov 10 00:00


def nov(day: int, hour: int = 0) -> float:
    """Day `day` of November 2026 (October 31 is 0, October 30 is -1) at `hour` UTC."""
    return T0 + (day - 1) * DAY + hour * HOUR


def pull(  # noqa: PLR0913  # one row of the spec's table
    number: int,
    ticket: str | None,
    opened: float,
    *,
    merged: float | None = None,
    review: float | None = None,
    lines: int | None = None,
    autonomy: AutonomyClass = AutonomyClass.UNKNOWN,
    state: PullState = PullState.OPEN,
    pulls: int = 1,
    title: str = "A change",
) -> PullFact:
    return PullFact(
        url=f"https://github.com/sample/sample/pull/{number}",
        repository="sample",
        number=number,
        ticket_id=ticket,
        title=title,
        opened_at=opened,
        state=PullState.MERGED if merged is not None else state,
        merged_at=merged,
        first_review_at=review,
        changed_lines=lines,
        autonomy=autonomy,
        ticket_pulls=pulls,
    )


A, S, U = AutonomyClass.AUTONOMOUS, AutonomyClass.ASSISTED, AutonomyClass.UNKNOWN

P0 = pull(10, "CF-0", nov(-1), merged=nov(2, 8), lines=10, autonomy=A, title="Earlier work")
P1 = pull(11, "CF-1", nov(2, 10), merged=nov(2, 14), review=nov(2, 11), lines=40, autonomy=A,
          title="Add the loader")  # fmt: skip
P2 = pull(12, "CF-2", nov(3, 10), merged=nov(4, 10), review=nov(3, 16), lines=100, autonomy=S,
          title="Split the loader")  # fmt: skip
P3 = pull(13, "CF-3", nov(5, 12), merged=nov(9, 12), review=nov(6, 12), lines=499, autonomy=A,
          title="Retry the fetch")  # fmt: skip
P4 = pull(14, "CF-4", nov(6, 8), lines=1000, title="Cache the index")
P5 = pull(15, "CF-5", nov(6, 9), lines=500, state=PullState.CLOSED, title="Drop the shim")
P6 = pull(16, "CF-6", nov(7, 10), lines=999, pulls=2, title="Page the list")
P7 = pull(17, "CF-6", nov(7, 11), merged=nov(8, 2), lines=99, pulls=2, title="Trim the page")

# Pull requests as the opened port answers for R1, and as the merged port answers.
OPENED_R1 = [P1, P2, P3, P4, P5, P6, P7]
MERGED_R1 = [P0, P1, P2]
COHORT_IDS = ["CF-1", "CF-2", "CF-3", "CF-4", "CF-5", "CF-6"]


def run(  # noqa: PLR0913, PLR0917  # one row of the spec's table
    run_id: str,
    ticket: str | None,
    stage: str,
    agent: str,
    model: str,
    state: str,
    started: float,
    source: str = "board",
) -> RunFact:
    return RunFact(
        id=run_id,
        ticket_id=ticket,
        repository="sample",
        stage=stage,
        agent=agent,
        model=model,
        source=source,
        state=state,
        started_at=started,
    )


RUNS = [
    run("r01", "CF-1", "build", "builder", "opus", "finished", nov(2, 9)),
    run("r02", "CF-1", "review", "reviewer", "opus", "finished", nov(2, 12) + 1800),
    run("r03", "CF-2", "spec", "builder", "opus", "finished", nov(3, 8)),
    run("r04", "CF-2", "build", "builder", "sonnet", "finished", nov(3, 8) + 1800),
    run("r05", "CF-2", "review", "reviewer", "opus", "failed", nov(3, 16)),
    run("r06", "CF-3", "build", "builder", "opus", "stopped", nov(5, 6)),
    run("r07", "CF-4", "build", "builder", "opus", "finished", nov(6, 6)),
    run("r08", "CF-4", "review", "reviewer", "opus", "running", nov(6, 10)),
    run("r09", "CF-5", "build", "builder", "sonnet", "failed", nov(6, 7)),
    run("r10", "CF-6", "build", "builder", "sonnet", "finished", nov(7, 8)),
    run("r11", "CF-6", "review", "reviewer", "sonnet", "finished", nov(7, 12)),
    run("j01", None, "judge", "judge", "sonnet", "finished", nov(4, 3), source="judge"),
    run("e01", None, "eval", "builder", "opus", "finished", nov(4, 4), source="eval"),
]

COSTS = {
    "r01": RunCost(cost=1.0),
    "r02": RunCost(cost=0.5),
    "r03": RunCost(cost=0.5),
    "r04": RunCost(cost=3.0),
    "r05": RunCost(cost=1.5),
    "r06": RunCost(cost=2.0),
    "r07": RunCost(cost=8.0),
    "r08": RunCost(cost=2.0),
    "r09": RunCost(cost=None),
    "r10": RunCost(cost=2.0),
    "r11": RunCost(cost=1.0),
    "j01": RunCost(cost=0.1),
    "e01": RunCost(cost=0.4),
}


def runs_of(*tickets: str) -> list[RunFact]:
    """Every run of these tickets."""
    return [r for r in RUNS if r.ticket_id in tickets]


CARD = ScorerCard(
    repository="sample",
    name="ran-tests",
    question="Did the agent run the tests before finishing?",
    yes=3,
    no=1,
    unclear=1,
    average_score=None,
    window_since=1793664000.0,
    window_until=1794268800.0,
)
