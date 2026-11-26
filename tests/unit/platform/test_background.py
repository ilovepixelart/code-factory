import asyncio
import logging

import pytest

from code_factory.platform.background import BackgroundTasks, background_tasks


async def test_a_task_is_referenced_while_it_runs_and_cancelled_at_shutdown() -> None:
    started = asyncio.Event()

    async def forever() -> None:
        started.set()
        await asyncio.Event().wait()

    async with background_tasks() as tasks:
        task = tasks.start("probe", forever)
        await started.wait()
        assert tasks.names == ["probe"]
        assert not task.done()
    assert task.cancelled()
    assert tasks.names == []


async def test_a_failing_task_is_logged_and_does_not_stop_its_sibling(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sibling_finished = asyncio.Event()

    async def fails() -> None:
        msg = "boom"
        raise RuntimeError(msg)

    async def sibling() -> None:
        await asyncio.sleep(0.05)
        sibling_finished.set()

    async with background_tasks() as tasks:
        tasks.start("fails", fails)
        tasks.start("sibling", sibling)
        await asyncio.wait_for(sibling_finished.wait(), timeout=2)
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR] == [
        "background task fails failed"
    ]


async def test_a_running_name_is_refused_and_shutdown_still_ends_every_task() -> None:
    async def forever() -> None:
        await asyncio.Event().wait()

    async with asyncio.timeout(2):
        async with background_tasks() as tasks:
            first = tasks.start("poller", forever)
            with pytest.raises(ValueError, match="background task poller is already running"):
                tasks.start("poller", forever)
            assert tasks.names == ["poller"]
    assert first.cancelled()


async def test_a_name_can_be_reused_once_its_task_has_finished() -> None:
    async def once() -> None:
        return

    async with background_tasks() as tasks:
        first = tasks.start("job", once)
        await first
        second = tasks.start("job", once)
        await second
    assert first is not second


async def test_a_task_cannot_start_before_the_application_runs() -> None:
    async def never() -> None:
        pytest.fail("the task must not run")

    with pytest.raises(RuntimeError, match="cannot start background task early: the application"):
        BackgroundTasks().start("early", never)
