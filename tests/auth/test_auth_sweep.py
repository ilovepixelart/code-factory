"""The hourly sweep of ended tokens, started by the app's lifespan."""

import asyncio
import logging
from datetime import timedelta

import pytest
from auth_clock import Clock
from sqlalchemy.ext.asyncio import AsyncConnection

from code_factory.auth.module import module
from code_factory.auth.service import AuthService, sweep_forever
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine
from code_factory.platform.module import Resources
from code_factory.platform.services import Services
from mcp_support import isolated_unit_of_work


async def test_the_loop_deletes_tokens_that_ended_over_a_day_ago(
    connection: AsyncConnection,
) -> None:
    clock = Clock()
    auth = AuthService(isolated_unit_of_work(connection), clock=clock)
    old = await auth.issue_owner_token("old", lifetime=timedelta(hours=1))
    clock.advance(timedelta(days=2))
    kept = await auth.issue_owner_token("kept", lifetime=timedelta(days=1))
    swept = asyncio.Event()

    class Watched:
        async def sweep_expired(self) -> int:
            count = await auth.sweep_expired()
            swept.set()
            return count

    task = asyncio.create_task(sweep_forever(Watched(), interval_s=0.01))
    try:
        await asyncio.wait_for(swept.wait(), timeout=5)
    finally:
        task.cancel()
    # The loop is cancelled before the connection is used again: it is not shared between tasks.
    await asyncio.gather(task, return_exceptions=True)
    ids = {info.id for info in await auth.list_tokens(include_ended=True)}
    assert ids == {kept.id}
    assert old.id not in ids


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


async def test_the_module_starts_the_sweep_when_the_app_starts(
    offline_settings: Settings, uow: UnitOfWork
) -> None:
    services = Services()
    tasks = BackgroundTasks()
    assert module.provide is not None
    assert module.background is not None
    module.provide(
        services, Resources(offline_settings, create_engine(offline_settings), uow, tasks)
    )
    async with tasks.run():
        module.background(services, tasks)
        assert tasks.names == ["auth-sweep"]


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
