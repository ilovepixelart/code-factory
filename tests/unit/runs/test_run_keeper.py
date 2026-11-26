"""The keeper loop: one recovery pass, then collection often and housekeeping less often."""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

import pytest

from code_factory.runs.models import Ended, PreviewRecord
from code_factory.runs.service.keeper import run_keeper
from runs_values import NOW

INTERVAL = 0.01


class Recorder:
    """Stands in for the three services: every call is kept, in order, as `name`."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.collect_failures = 0
        self.withdrawn_before: list[datetime] = []

    async def collect(self, now: datetime | None = None) -> list[Ended]:  # noqa: ARG002
        self.calls.append("collect")
        if self.collect_failures:
            self.collect_failures -= 1
            msg = "the database is busy"
            raise RuntimeError(msg)
        return []

    async def withdraw_pending(self, before: datetime) -> int:
        self.calls.append("withdraw")
        self.withdrawn_before.append(before)
        return 0

    async def expire(self, now: datetime) -> list[object]:  # noqa: ARG002
        self.calls.append("expire")
        return []

    async def prune(self, now: datetime) -> int:  # noqa: ARG002
        self.calls.append("prune")
        return 0

    async def running(self) -> list[PreviewRecord]:
        self.calls.append("previews")
        return []


async def keeping(rec: Recorder, until: Callable[[Recorder], bool], *, every: float = 0.05) -> None:
    """Run the keeper until `until(rec)` holds (or five seconds pass), then cancel it."""
    task = asyncio.create_task(
        run_keeper(rec, rec, rec, interval=INTERVAL, housekeeping_every=every, clock=lambda: NOW)
    )
    async with asyncio.timeout(5):
        while not until(rec):  # noqa: ASYNC110  # the keeper is the thing under test
            await asyncio.sleep(0.001)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_nothing_is_touched_before_the_first_interval_has_passed() -> None:
    rec = Recorder()
    task = asyncio.create_task(run_keeper(rec, rec, rec, interval=60, clock=lambda: NOW))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert rec.calls == []


async def test_the_first_pass_withdraws_the_old_requests_then_collects() -> None:
    rec = Recorder()
    await keeping(rec, lambda r: "collect" in r.calls)
    assert rec.calls[:2] == ["withdraw", "collect"]
    assert rec.calls.count("withdraw") == 1


async def test_the_recovery_leaves_the_requests_made_after_the_keeper_started() -> None:
    rec = Recorder()
    await keeping(rec, lambda r: "collect" in r.calls)
    assert rec.withdrawn_before == [NOW]


async def test_collection_repeats_every_interval() -> None:
    rec = Recorder()
    await keeping(rec, lambda r: r.calls.count("collect") >= 5)
    assert rec.calls.count("withdraw") == 1


async def test_housekeeping_runs_less_often_than_collection() -> None:
    rec = Recorder()
    await keeping(rec, lambda r: r.calls.count("expire") >= 2, every=0.1)
    assert rec.calls.count("expire") <= rec.calls.count("collect") // 5 + 1
    assert rec.calls.count("expire") == rec.calls.count("prune") == rec.calls.count("previews")


async def test_a_failing_pass_is_logged_and_the_loop_goes_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rec = Recorder()
    rec.collect_failures = 2
    with caplog.at_level(logging.ERROR):
        await keeping(rec, lambda r: r.calls.count("collect") >= 5)
    assert "the run keeper's collection failed" in caplog.text
    assert "the database is busy" in caplog.text


async def test_cancelling_the_keeper_stops_its_calls() -> None:
    rec = Recorder()
    await keeping(rec, lambda r: r.calls.count("collect") >= 2)
    seen = len(rec.calls)
    await asyncio.sleep(0.05)
    assert len(rec.calls) == seen
