"""The factory service over in-memory providers: fixture F1, the golden answer and the errors."""

import json
import random
import time

import pytest
from factory_fakes import FakeCosts, FakeImprovements, FakePulls, FakeRuns, FakeScorers
from factory_values import (
    CARD,
    COSTS,
    DAY,
    NOW,
    OPENED_R1,
    P0,
    P2,
    RUNS,
    nov,
    pull,
    run,
)

from code_factory.factory.models import (
    AutonomyClass,
    ImprovementPR,
    Improvements,
    PullState,
    RunCost,
    ScorerCards,
)
from code_factory.factory.ports import (
    CostPort,
    ImprovementPort,
    PullsPort,
    RunsPort,
    ScorerPort,
)
from code_factory.factory.service import FactoryPorts, FactoryService
from code_factory.platform.errors import BadRequestError, UnavailableError
from repo_files import ROOT

GOLDEN = ROOT / "tests" / "golden" / "factory" / "dashboard.golden.json"
ALL_PULLS = [P0, *OPENED_R1]


class World:
    """The five fakes of one test, and the service over them."""

    def __init__(self, now: float = NOW) -> None:
        self.runs = FakeRuns().holding(RUNS)
        self.pulls = FakePulls().holding(ALL_PULLS)
        self.costs = FakeCosts().holding(COSTS)
        self.scorers = FakeScorers().holding(ScorerCards(available=True, cards=[CARD]))
        self.improvements = FakeImprovements().holding(Improvements(available=False))
        self.service = FactoryService(
            FactoryPorts(self.runs, self.pulls, self.costs, self.scorers, self.improvements),
            now=lambda: now,
        )

    def calls(self) -> list[str]:
        fakes = (self.runs, self.pulls, self.costs, self.scorers, self.improvements)
        return [name for fake in fakes for name, _ in fake.calls]


def test_the_fakes_satisfy_the_ports() -> None:
    world = World()
    assert isinstance(world.runs, RunsPort)
    assert isinstance(world.pulls, PullsPort)
    assert isinstance(world.costs, CostPort)
    assert isinstance(world.scorers, ScorerPort)
    assert isinstance(world.improvements, ImprovementPort)


async def test_the_dashboard_of_the_first_week_is_the_hand_written_golden() -> None:
    got = await World().service.dashboard("2026-11-01", "2026-11-08")
    assert got.model_dump(mode="json", by_alias=True) == json.loads(GOLDEN.read_text())


async def test_the_dashboard_makes_seven_bulk_calls_and_none_per_pull_request() -> None:
    world = World()
    await world.service.dashboard("2026-11-01", "2026-11-08")
    assert sorted(world.calls()) == sorted(
        ["runs", "opened", "merged", "for_tickets", "costs", "cards", "newest"]
    )


async def test_the_ticket_runs_are_asked_for_once_with_the_cohorts_ticket_ids() -> None:
    world = World()
    await world.service.dashboard("2026-11-01", "2026-11-08")
    (ids,) = [args[0] for name, args in world.runs.calls if name == "for_tickets"]
    assert sorted(ids) == ["CF-1", "CF-2", "CF-3", "CF-4", "CF-5", "CF-6"]


async def test_costs_are_asked_for_once_covering_range_runs_and_ticket_runs() -> None:
    world = World()
    await world.service.dashboard("2026-11-01", "2026-11-08")
    (ids,) = [args[0] for name, args in world.costs.calls if name == "costs"]
    assert sorted(ids) == sorted(r.id for r in RUNS)


async def test_the_newest_three_improvements_are_asked_for() -> None:
    world = World()
    await world.service.dashboard("2026-11-01", "2026-11-08")
    assert [args for name, args in world.improvements.calls] == [(3,)]


async def test_the_second_week_has_more_merges_than_openings() -> None:
    # P7 merged Nov 8 02:00 and P3 Nov 9 12:00, both inside [Nov 8, Nov 15); nothing opened.
    world = World(now=nov(15))
    got = await world.service.dashboard("2026-11-08", "2026-11-15")
    assert (got.prs.opened, got.prs.merged, got.prs.merged_in_period) == (0, 0, 2)


async def test_the_kickoff_is_the_earliest_run_of_the_ticket_even_before_the_range() -> None:
    # CF-2 has a spec run Oct 31 12:00, before the range [Nov 1, Nov 8). P2 opened Nov 3 10:00
    # (70 h later) and merged Nov 4 10:00 (94 h after the kickoff).
    world = World()
    early = run("r00", "CF-2", "spec", "builder", "opus", "finished", nov(0, 12))
    world.runs.holding([early, *RUNS])
    world.pulls.holding([P2])
    got = await world.service.dashboard("2026-11-01", "2026-11-08")
    stages = {s.stage: s.median for s in got.cycle.stages}
    assert got.cycle.total.median == 94 * 3600
    assert stages["kickoff_to_pr"] == 70 * 3600


async def test_a_range_with_no_data_answers_zeros_and_nulls_without_error() -> None:
    world = World()
    got = await world.service.dashboard("2026-01-01", "2026-01-08")
    assert got.runs.total == 0
    assert got.prs.opened == 0
    assert got.autonomy.share is None
    assert (got.cycle.total.median, got.cycle.total.count) == (None, 0)
    assert (got.cost.median, got.cost.of) == (None, 0)
    assert got.expensive == []
    assert len(got.series.points) == 7
    assert {(p.opened, p.merged) for p in got.series.points} == {(0, 0)}
    assert "for_tickets" not in world.calls()


async def test_a_null_scorer_provider_says_unavailable_with_no_cards() -> None:
    world = World()
    world.scorers.holding(ScorerCards(available=False))
    got = await world.service.dashboard("2026-11-01", "2026-11-08")
    assert (got.scorers.available, got.scorers.cards) == (False, [])


async def test_a_provider_that_cannot_answer_fails_the_call_with_its_sentence() -> None:
    world = World()
    world.pulls.refuses = "the delivery module is not reachable"
    with pytest.raises(UnavailableError, match=r"^the delivery module is not reachable$"):
        await world.service.dashboard("2026-11-01", "2026-11-08")


async def test_a_run_with_no_cost_record_reads_as_unpriced() -> None:
    world = World()
    world.costs.holding({k: v for k, v in COSTS.items() if k != "r07"})
    got = await world.service.dashboard("2026-11-01", "2026-11-08")
    assert got.expensive[0].number == 12  # CF-4 lost its 8.00 build run
    assert [(s.size.value, s.median) for s in got.cost.by_size][3] == ("XL", 2.0)


async def test_a_bad_range_is_refused_before_any_provider_is_asked() -> None:
    world = World()
    with pytest.raises(BadRequestError, match=r"^from must be before to$"):
        await world.service.dashboard("2026-11-08", "2026-11-01")
    assert world.calls() == []


async def test_the_runs_answer_is_the_runs_object_of_the_dashboard() -> None:
    world = World()
    got = await world.service.runs("2026-11-01", "2026-11-08")
    assert (got.total, got.by_stage[0].key, got.by_stage[0].runs) == (13, "build", 6)
    assert world.calls() == ["runs"]


async def test_the_expensive_answer_lists_the_top_three() -> None:
    got = await World().service.expensive("2026-11-01", "2026-11-08", "3")
    assert [p.number for p in got.prs] == [14, 12, 13]


async def test_the_expensive_answer_defaults_to_ten() -> None:
    got = await World().service.expensive("2026-11-01", "2026-11-08", None)
    assert len(got.prs) == 6  # six are priced; the default limit of 10 does not cut them


@pytest.mark.parametrize("limit", ["0", "51", "x"])
async def test_a_bad_expensive_limit_is_refused_before_any_provider_is_asked(limit: str) -> None:
    world = World()
    with pytest.raises(BadRequestError, match=r"^limit must be a whole number from 1 to 50$"):
        await world.service.expensive("2026-11-01", "2026-11-08", limit)
    assert world.calls() == []


async def test_the_scorers_answer_adds_asked_and_pass_rate() -> None:
    got = await World().service.scorers("2026-11-01", "2026-11-08")
    (card,) = got.cards
    assert (got.available, card.asked, card.pass_rate) == (True, 5, 0.75)


async def test_the_improvements_answer_takes_a_limit_from_one_to_fifty_default_three() -> None:
    items = [
        ImprovementPR(
            url=f"https://github.com/sample/sample/pull/{n}",
            number=n,
            title=f"Self-improvement: {n} failures",
            state=PullState.OPEN,
            opened_at=1794000000.0 - n,
            failures=25,
        )
        for n in range(1, 8)
    ]
    world = World()
    world.improvements.holding(Improvements(available=True, items=items))
    assert [i.number for i in (await world.service.improvements(None)).items] == [1, 2, 3]
    assert len((await world.service.improvements("5")).items) == 5
    with pytest.raises(BadRequestError, match=r"^limit must be a whole number from 1 to 50$"):
        await world.service.improvements("0")


async def test_a_large_cohort_is_answered_in_seven_calls_and_inside_the_budget() -> None:
    rng = random.Random(7)  # noqa: S311  # seeded for a reproducible set, not security
    pulls, runs, costs = [], [], {}
    for n in range(300):
        ticket = f"CF-{n}"
        opened = nov(1) + rng.random() * 6 * DAY
        merged = opened + rng.random() * 2 * DAY if n % 2 else None
        pulls.append(
            pull(n, ticket, opened, merged=merged, lines=n * 7, autonomy=AutonomyClass.AUTONOMOUS)
        )
        for k in range(10):
            started = nov(1) + rng.random() * 6 * DAY
            runs.append(run(f"r{n}-{k}", ticket, "build", "builder", "opus", "finished", started))
            costs[f"r{n}-{k}"] = RunCost(cost=rng.random())
    world = World()
    world.pulls.holding(pulls)
    world.runs.holding(runs)
    world.costs.holding(costs)
    got = await world.service.dashboard("2026-11-01", "2026-11-08")  # warms imports and caches
    assert (got.prs.opened, len(world.calls())) == (300, 7)
    elapsed = []
    for _ in range(5):
        begun = time.perf_counter()
        await world.service.dashboard("2026-11-01", "2026-11-08")
        elapsed.append(time.perf_counter() - begun)
    assert min(elapsed) < 0.15  # the best of five: a loaded machine slows a run, not the work
