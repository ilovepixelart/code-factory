"""The sweep: which rows it ends and drops, and the loop that runs it."""

import asyncio
import logging
from datetime import timedelta

import pytest

from broker_harness import NOW, Builder, Clock, FakeControl, issue, serving
from code_factory.broker.models import SweepReport
from code_factory.broker.repository import BrokerRepository
from code_factory.broker.service import BrokerService
from code_factory.platform.db import UnitOfWork


async def test_a_token_whose_run_the_control_says_is_gone_is_ended_and_its_row_dropped(
    make: Builder, control: FakeControl
) -> None:
    service = make()
    service.attach_run_control(control)
    control.active = {"alive"}
    async with serving(service):
        await _tokens(service, "alive", "gone")
        report = await service.sweep()
        assert report.dropped_tokens == 1
        assert await service.describe("gone") is None
        alive = await service.describe("alive")
    assert alive is not None
    assert not alive.ended


async def _tokens(service: BrokerService, *runs: str) -> None:
    for run in runs:
        await issue(service, run, None)


async def test_with_no_control_attached_only_the_expiry_ends_a_token(
    make: Builder, clock: Clock
) -> None:
    service = make()
    async with serving(service):
        await _tokens(service, "r1")
        first = await service.sweep()
        assert first.dropped_tokens == 0
        clock.now = NOW + timedelta(hours=2)
        second = await service.sweep()
        assert second.dropped_tokens == 1
        assert await service.describe("r1") is None


async def test_a_control_that_does_not_answer_ends_nothing(
    make: Builder, control: FakeControl, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = make()
    service.attach_run_control(control)

    async def hang(ids: object) -> set[str]:  # noqa: ARG001
        await asyncio.sleep(30)
        return set()

    monkeypatch.setattr("code_factory.broker.service.sweeping.CONTROL_S", 0.1)
    monkeypatch.setattr(control, "active_run_ids", hang)
    async with serving(service):
        await _tokens(service, "r1")
        await service.sweep()
        info = await service.describe("r1")
    assert info is not None
    assert not info.ended


async def test_the_loop_runs_a_pass_at_once_then_every_interval_and_ends_on_stop(
    make: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = make(broker_sweep_interval_s=0.05)
    passes = 0

    async def counted() -> SweepReport:
        nonlocal passes
        passes += 1
        return SweepReport()

    monkeypatch.setattr(service, "sweep", counted)
    stop = asyncio.Event()
    task = asyncio.create_task(service.sweep_loop(stop))
    await asyncio.sleep(0.02)
    assert passes == 1  # the pass at start, before the first interval
    await asyncio.sleep(0.3)
    assert passes >= 3
    stop.set()
    await asyncio.wait_for(task, 1)


async def test_a_failing_pass_is_logged_and_the_loop_goes_on(
    make: Builder, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    service = make(broker_sweep_interval_s=0.05)
    passes = 0

    async def flaky() -> SweepReport:
        nonlocal passes
        passes += 1
        if passes == 1:
            msg = "the database is busy"
            raise RuntimeError(msg)
        return SweepReport()

    monkeypatch.setattr(service, "sweep", flaky)
    stop = asyncio.Event()
    with caplog.at_level(logging.ERROR):
        task = asyncio.create_task(service.sweep_loop(stop))
        await asyncio.sleep(0.25)
        stop.set()
        await asyncio.wait_for(task, 1)
    assert passes >= 2
    assert any("a broker sweep failed" in r.getMessage() for r in caplog.records)


async def test_cancelling_the_loop_is_not_swallowed(
    make: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = make(broker_sweep_interval_s=30)

    async def quiet() -> SweepReport:
        return SweepReport()

    monkeypatch.setattr(service, "sweep", quiet)
    task = asyncio.create_task(service.sweep_loop(asyncio.Event()))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_run_that_ends_holding_a_key_wakes_the_sweep_before_its_interval(
    make: Builder, monkeypatch: pytest.MonkeyPatch, real_uow: UnitOfWork
) -> None:
    service = make(broker_sweep_interval_s=30)
    passes = 0

    async def counted() -> SweepReport:
        nonlocal passes
        passes += 1
        return SweepReport()

    monkeypatch.setattr(service, "sweep", counted)
    async with serving(service):
        await _tokens(service, "r1")
        async with real_uow() as session:
            repo = BrokerRepository(session)
            await repo.set_state("r1", ("none",), "making", NOW)
            await repo.set_state("r1", ("making",), "made", NOW, "k1")
        stop = asyncio.Event()
        task = asyncio.create_task(service.sweep_loop(stop))
        await asyncio.sleep(0.05)
        assert passes == 1
        await service.end_run("r1")
        await asyncio.sleep(0.1)
        assert passes == 2
        stop.set()
        await asyncio.wait_for(task, 1)
