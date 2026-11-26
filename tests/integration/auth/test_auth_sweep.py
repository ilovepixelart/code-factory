"""The hourly sweep of ended tokens, started by the app's lifespan."""

import asyncio
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncConnection

from auth_clock import Clock
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
