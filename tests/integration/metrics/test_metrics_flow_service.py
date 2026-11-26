"""`MetricsService.flow` through the fakes and the real ledger, against the golden pages."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from test_metrics_refresh import record

from code_factory.metrics.service import MetricsService
from git_support import ENV, git
from metrics_support import (
    DAY,
    HOUR,
    NOW,
    World,
    at_time,
    commit_at,
    pull_request,
    run_facts,
    ticket,
    when,
)
from repo_files import ROOT

GOLDEN = ROOT / "tests" / "support" / "golden" / "formats" / "metrics"
MERGED_AT = 1_790_000_240.0


def golden_cases() -> list[dict[str, Any]]:
    return json.loads((GOLDEN / "flow.golden.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]  # json


def golden_runs() -> list[Any]:
    """The runs of the golden state: those of `AB-1` belong to the second repository."""
    state = json.loads((GOLDEN / "state.json").read_text(encoding="utf-8"))
    return [
        run_facts(
            r["ticket_id"],
            r["started_at"],
            repository="second" if r["ticket_id"].startswith("AB-") else "sample",
            stage=r["stage"],
            model=r.get("model", ""),
            cost=r["cost"],
        )
        for r in state["runs"]
    ]


@pytest.fixture
def golden_world(world: World, root: Path, tmp_path: Path) -> World:
    """Pull 7 of `ticket/cf-50` merged at 1790000240, its ticket filed 180 s before."""
    world.now = NOW
    pull_request(root, 7, "ticket/cf-50", MERGED_AT - 60)
    world.tickets.facts["sample"] = [ticket("CF-50", MERGED_AT - 180, title="Idea 50")]
    second = tmp_path / "second"
    second.mkdir()
    git(second, "init", "-q", "-b", "main")
    commit_at(second, NOW - 40 * DAY, "Start")
    world.track(second)
    world.runs.runs = golden_runs()
    world.runs.starts = {
        "sample": {
            "CF-1": when(1_787_409_000.0),
            "CF-2": when(1_788_100_200.0),
            "CF-13": when(1_788_661_800.0),
        },
        "second": {"AB-1": when(1_788_705_000.0)},
    }
    return world


@pytest.mark.usefixtures("golden_world")
@pytest.mark.parametrize("case", range(3))
async def test_the_page_is_the_golden_page_of_each_range_but_for_its_hand_timed_columns(
    metrics: MetricsService, case: int
) -> None:
    expected = golden_cases()[case]
    await metrics.refresh()

    page = await metrics.flow(expected["query"].removeprefix("range=") or None)

    answered = page.model_dump(mode="json")
    answered.pop("columns")
    want = dict(expected["flow"])
    want.pop("columns")
    assert answered["merged"] == want["merged"]
    assert answered == want


@pytest.mark.usefixtures("golden_world")
async def test_an_unknown_range_reads_as_seven_days(metrics: MetricsService) -> None:
    await metrics.refresh()
    page = await metrics.flow("1y")
    assert (page.range, page.since) == ("7d", NOW - 7 * DAY)


async def test_with_no_tracked_repository_the_page_is_zeros_and_nulls(
    metrics: MetricsService, world: World
) -> None:
    world.repositories.repos.clear()
    page = await metrics.flow()
    assert page.merged == []
    assert (page.in_flight, page.stuck, page.stuck_after) == (0, [], DAY)
    assert (page.lead.median, page.lead.count, page.cost.of) == (None, 0, 0)
    assert page.agents == []


# Pulls 1 to 4 as the held history: #3 is the cause of bug CF-4, #2 is reverted by #4.
async def test_each_merge_says_whether_it_held(
    metrics: MetricsService, world: World, root: Path
) -> None:
    first = NOW - 4 * HOUR
    for number, branch in enumerate(["ticket/cf-1", "ticket/cf-2", "ticket/cf-3"], start=1):
        pull_request(root, number, branch, first + number * HOUR / 2)
    pull_request(
        root, 4, "revert/two", first + 2 * HOUR, "Revert the work of CF-2\n\nThis reverts #2."
    )
    world.tickets.facts["sample"] = [
        ticket("CF-1", first),
        ticket("CF-2", first),
        ticket("CF-3", first),
        ticket("CF-4", first, caused_by=("CF-3",)),
        ticket("CF-5", first),  # names CF-1 only in its text: no `fixes`
    ]
    world.checks.records_ = [
        record("CF-1", git(root, "rev-parse", "ticket/cf-1"), 0),
        record("CF-2", git(root, "rev-parse", "ticket/cf-2"), 1),
        record("CF-3", git(root, "rev-list", "--max-parents=0", "main"), 0),
    ]
    await metrics.refresh()

    page = await metrics.flow()

    assert [(m.pull, m.reverted, m.fixes, m.checks.value) for m in page.merged] == [
        (4, False, [], "none"),
        (3, False, ["CF-4"], "none"),
        (2, True, [], "failed"),
        (1, False, [], "passed"),
    ]


async def test_a_merge_links_to_its_pull_request_once_git_names_a_github_origin(
    metrics: MetricsService, root: Path
) -> None:
    pull_request(root, 7, "ticket/cf-1", NOW - HOUR)
    git(root, "remote", "set-url", "origin", "git@github.com:o/r.git")
    await metrics.refresh()
    [row] = (await metrics.flow()).merged
    assert row.url == "https://github.com/o/r/pull/7"
    git(root, "remote", "set-url", "origin", "git@github.com:o/changed.git")
    [again] = (await metrics.flow()).merged
    assert again.url == "https://github.com/o/r/pull/7"  # asked of git once


async def test_a_repository_whose_git_is_gone_still_answers_from_the_ledger(
    metrics: MetricsService, root: Path
) -> None:
    pull_request(root, 7, "ticket/cf-1", NOW - HOUR)
    await metrics.refresh()
    (root / ".git").rename(root / ".git-away")

    page = await metrics.flow()

    assert [(m.pull, m.url) for m in page.merged] == [(7, None)]


async def test_a_ticket_costs_the_sum_of_its_runs_and_the_page_their_median(
    metrics: MetricsService, world: World, root: Path
) -> None:
    pull_request(root, 1, "ticket/cf-1", NOW - 3 * HOUR)
    pull_request(root, 2, "ticket/cf-2", NOW - 2 * HOUR)
    world.tickets.facts["sample"] = [ticket("CF-1", NOW - DAY), ticket("CF-2", NOW - DAY)]
    world.runs.runs = [
        run_facts("CF-1", NOW - 5 * DAY, cost=1.0),  # started before the window: still its cost
        run_facts("CF-1", NOW - 4 * HOUR, cost=2.0),
        run_facts("CF-2", NOW - 4 * HOUR, cost=10.0),
    ]
    await metrics.refresh()

    page = await metrics.flow("24h")

    assert {m.ticket: m.cost for m in page.merged} == {"CF-1": 3.0, "CF-2": 10.0}
    assert page.cost.median == 3.0


async def test_a_branch_two_days_old_is_stuck_and_a_fresh_one_is_not(
    metrics: MetricsService, world: World, root: Path
) -> None:
    with patch.dict(ENV, at_time(NOW - 2 * DAY)):
        git(root, "branch", "ticket/cf-1")
    with patch.dict(ENV, at_time(NOW - HOUR)):
        git(root, "branch", "ticket/cf-2")
    world.tickets.facts["sample"] = [
        ticket("CF-1", NOW - 3 * DAY, stage="build", branch="ticket/cf-1", needs="a reviewer"),
        ticket("CF-2", NOW - 3 * DAY, stage="review", branch="ticket/cf-2"),
        ticket("CF-3", NOW - 3 * DAY, stage="build", branch="ticket/cf-3"),
        ticket("CF-4", NOW - 3 * DAY, stage="spec"),
    ]
    await metrics.refresh()

    page = await metrics.flow()

    assert page.in_flight == 3  # CF-3's branch does not exist, its cut is unknown
    assert [(s.id, s.stage, s.age, s.needs) for s in page.stuck] == [
        ("CF-1", "build", 2 * DAY, "a reviewer")
    ]


async def test_the_flow_read_asks_for_a_repository_with_no_merged_ticket_only_its_branches(
    metrics: MetricsService, world: World
) -> None:
    await metrics.flow()
    assert world.tickets.calls == [("sample", None, ["build", "review"])]


async def test_the_ledger_rows_of_an_untracked_repository_are_not_listed(
    metrics: MetricsService, world: World, root: Path, db_session: AsyncSession
) -> None:
    pull_request(root, 1, "ticket/cf-1", NOW - HOUR)
    await metrics.refresh()
    world.repositories.repos.clear()
    assert (await metrics.flow()).merged == []
    count = await db_session.scalar(text("select count(*) from metrics_merges"))
    assert count == 1


async def test_a_merge_of_a_ticket_filed_after_it_merged_is_measured_from_the_first_commit(
    metrics: MetricsService, world: World, root: Path
) -> None:
    pull_request(root, 1, "ticket/cf-1", NOW - 2 * HOUR)
    world.tickets.facts["sample"] = [ticket("CF-1", NOW)]
    await metrics.refresh()
    [row] = (await metrics.flow()).merged
    assert (row.from_, row.lead) == ("first_commit", 60.0)  # the branch's commit, a minute earlier
