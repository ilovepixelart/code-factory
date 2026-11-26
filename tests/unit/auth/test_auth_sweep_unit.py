"""The hourly sweep of ended tokens, started by the app's lifespan."""

import asyncio
import logging

import pytest

from code_factory.auth.service import sweep_forever


async def test_a_failed_pass_is_logged_and_the_loop_goes_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls = 0

    class Flaky:
        async def sweep_expired(self) -> int:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("database went away")
            return 0

    task = asyncio.create_task(sweep_forever(Flaky(), interval_s=0.01))
    try:
        for _ in range(200):
            await asyncio.sleep(0.01)
            if calls >= 2:
                break
    finally:
        task.cancel()
    assert calls >= 2
    assert any("token sweep failed" in r.getMessage() for r in caplog.records)
    assert caplog.records[0].levelno == logging.ERROR


async def test_the_first_pass_waits_one_interval() -> None:
    calls = 0

    class Counting:
        async def sweep_expired(self) -> int:
            nonlocal calls
            calls += 1
            return 0

    task = asyncio.create_task(sweep_forever(Counting(), interval_s=3600))
    await asyncio.sleep(0.05)
    task.cancel()
    assert calls == 0
