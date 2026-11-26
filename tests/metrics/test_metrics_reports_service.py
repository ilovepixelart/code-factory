"""Step times, the `times` report, throughput, forecast and yields through the service."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from code_factory.metrics.models import StageMove, StepRun
from code_factory.metrics.service import MetricsService
from code_factory.platform.background import background_tasks
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, NotFoundError
from git_log_values import SHIPPED
from metrics_support import DAY, HOUR, NOW, World, pull_request, run_facts, ticket, when

HEADER = "step         runs  median  slowest  passed  failed  flaky  waited  slowest on\n"


def step_run(ticket_id: str, at: str, seconds: dict[str, int] | None = None) -> StepRun:
    return StepRun(
        ticket_id=ticket_id,
        at=datetime.fromisoformat(at),
        seconds=seconds or {},
        states={},
        retried=[],
        lock_waits={},
        slept=False,
    )


def three_runs() -> list[StepRun]:
    return [
        step_run("CF-1", "2026-09-21T10:00:00+00:00", {"rust-test": 30, "web-build": 2}),
        step_run("CF-2", "2026-09-21T09:00:00+00:00"),
        step_run("CF-2", "2026-09-21T11:00:00+00:00", {"rust-test": 50}),
        step_run("CF-3", "2026-09-21T12:00:00+00:00", {"rust-test": 90, "web-build": 1}),
    ]


@pytest.mark.parametrize("last", [0, -1])
async def test_a_window_of_fewer_than_one_run_is_refused(
    metrics: MetricsService, last: int
) -> None:
    with pytest.raises(BadRequestError, match="last must be at least 1"):
        await metrics.step_times(last)
    with pytest.raises(BadRequestError, match="last must be at least 1"):
        await metrics.times_report(last)


async def test_one_run_is_a_window_and_none_reads_every_run(
    metrics: MetricsService, world: World
) -> None:
    world.checks.steps = three_runs()
    assert [s.runs for s in await metrics.step_times(1)] == [1, 1]
    assert [s.runs for s in await metrics.step_times()] == [3, 2]


async def test_the_times_text_is_the_step_table_of_the_recorded_runs(
    metrics: MetricsService, world: World
) -> None:
    world.checks.steps = three_runs()
    report = await metrics.times_report()
    assert report.text == (
        f"{HEADER}"
        "rust-test       3      50       90    100%      0%     0%       0  CF-3\n"
        "web-build       2       1        2    100%      0%     0%       0  CF-1\n"
    )
    assert report.since == datetime(2026, 9, 21, 10, 0, tzinfo=UTC).timestamp()
    assert (report.merges, report.reverted, report.columns) == (0, 0, [])


async def test_with_no_recorded_run_the_report_says_so(metrics: MetricsService) -> None:
    report = await metrics.times_report()
    assert report.text == "no gate run has recorded step times yet\n"
    assert (report.steps, report.since) == ([], None)


async def test_an_unknown_repository_is_not_found(metrics: MetricsService) -> None:
    with pytest.raises(NotFoundError, match="nope"):
        await metrics.times_report(repository="nope")
    with pytest.raises(NotFoundError, match="nope"):
        await metrics.throughput("nope")
    with pytest.raises(NotFoundError, match="nope"):
        await metrics.forecast(repository="nope")
    with pytest.raises(NotFoundError, match="nope"):
        await metrics.factory("nope")


async def test_the_report_adds_the_columns_and_the_reverts_since_the_oldest_run(
    metrics: MetricsService, world: World, root: Path
) -> None:
    since = datetime(2026, 9, 21, 10, 0, tzinfo=UTC).timestamp()
    world.checks.steps = [step_run("CF-1", "2026-09-21T10:00:00+00:00", {"lint": 5})]
    world.tickets.facts["sample"] = [
        ticket("CF-1", since - HOUR, stage="build", moves=[(since + 20 * 60, "build")]),
        ticket("CF-2", since - DAY, stage="spec"),  # last move before the window
    ]
    pull_request(root, 1, "ticket/cf-1", since + 60)
    pull_request(root, 2, "revert/one", since + 120, "Revert\n\nThis reverts #1.")
    await metrics.refresh()

    report = await metrics.times_report()

    assert (report.merges, report.reverted) == (2, 1)
    assert (
        "\nminutes in each column of the tickets that moved since 2026-09-21T10:00:00Z\n"
        "ticket       spec  build review  now\n"
        "CF-1           80    250      -  build\n"
    ) in report.text
    assert "merges since 2026-09-21T10:00:00Z: 2, reverted later: 1 (50%)\n" in report.text
    assert [c.ticket for c in report.columns] == ["CF-1"]


async def test_throughput_counts_the_week_a_ticket_reached_review(
    metrics: MetricsService, world: World
) -> None:
    world.tickets.facts["sample"] = [
        ticket("CF-1", NOW - 3 * DAY, moves=[(NOW - 2 * DAY, "review")]),
        ticket("CF-2", NOW - 3 * DAY, stage="build", moves=[(NOW - 2 * DAY, "build")]),
    ]
    assert sum(await metrics.throughput()) == 1


async def test_the_forecast_defaults_to_the_tickets_before_review_and_none_says_nothing(
    metrics: MetricsService, world: World
) -> None:
    world.tickets.facts["sample"] = [
        ticket("CF-1", NOW - 3 * DAY, stage="spec"),
        ticket("CF-2", NOW - 3 * DAY, stage="build"),
        ticket("CF-3", NOW - 3 * DAY, stage="review"),
        ticket("CF-4", NOW - 3 * DAY, stage="spec", archived=True),
    ]
    nothing = await metrics.forecast()
    assert (nothing.open, nothing.p50, nothing.p85) == (2, None, None)
    assert len(nothing.sample) == 56
    assert (await metrics.forecast(0)).p50 == 0


async def test_a_negative_open_count_is_refused_and_zero_is_not(metrics: MetricsService) -> None:
    with pytest.raises(BadRequestError, match="open must be at least 0"):
        await metrics.forecast(-1)
    assert (await metrics.forecast(0)).open == 0


async def test_the_factory_view_counts_merged_work_that_held(
    metrics: MetricsService, world: World, root: Path
) -> None:
    pull_request(root, 1, "ticket/cf-1", NOW - 3 * HOUR)
    pull_request(root, 2, "ticket/cf-2", NOW - 2 * HOUR)
    world.tickets.facts["sample"] = [
        ticket("CF-1", NOW - DAY),
        ticket("CF-2", NOW - DAY),
        ticket("CF-9", NOW - HOUR, caused_by=("CF-2",)),
    ]
    world.runs.runs = [
        run_facts("CF-1", NOW - 5 * HOUR, stage="spec", agent="coder", cost=1.0),
        run_facts("CF-1", NOW - 4 * HOUR, agent="coder", cost=2.0),
        run_facts("CF-2", NOW - 4 * HOUR, agent="coder"),
        run_facts("CF-3", NOW - 4 * HOUR, agent="coder", exit_code=1),
    ]
    await metrics.refresh()

    [only] = await metrics.factory()

    assert (only.agent, only.runs, only.unfinished, only.merged, only.held) == ("coder", 4, 1, 2, 1)
    assert (only.end_to_end, only.cost) == (1, 3.0)


async def test_a_clean_exit_that_committed_nothing_counts_as_unfinished(
    metrics: MetricsService, world: World
) -> None:
    world.runs.runs = [
        run_facts("CF-1", NOW - 5 * HOUR, agent="coder", commits=[]),
        run_facts("CF-1", NOW - 4 * HOUR, agent="coder", commits=["abc"]),
        run_facts("CF-1", NOW - 3 * HOUR, agent="coder", commits=None),
    ]

    [only] = await metrics.factory()

    assert (only.runs, only.unfinished) == (3, 1)


def test_other_modules_read_when_a_ticket_reached_review_from_its_moves() -> None:
    moves = [
        StageMove(at=when(10.0), to="build"),
        StageMove(at=when(20.0), to="review"),
        StageMove(at=when(30.0), to="merged"),
    ]
    assert MetricsService.reached_done(moves) == when(20.0)
    assert MetricsService.reached_done(moves[:1]) is None


def test_other_modules_parse_a_merge_log() -> None:
    assert [m.pull for m in MetricsService.merges_in_log(SHIPPED)] == [9, 7]
    assert [m.pull for m in MetricsService.merges_in_log(SHIPPED, 1600.0)] == [9]


async def test_the_loop_refreshes_at_once_and_ends_on_cancel_within_a_second(
    uow: UnitOfWork, world: World, root: Path
) -> None:
    service = world.service(uow, loop_interval_s=3600.0)
    pull_request(root, 1, "ticket/cf-1", NOW - HOUR)
    async with background_tasks() as tasks:
        task = tasks.start("metrics-refresh", service.run_refresh_loop)
        async with asyncio.timeout(5):
            await world.repositories.begun.wait()  # a pass began, long before the interval
        assert tasks.names == ["metrics-refresh"]
        task.cancel()
        async with asyncio.timeout(1):
            await asyncio.wait({task})
    assert task.cancelled() or task.done()
    assert tasks.names == []
