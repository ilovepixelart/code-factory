import asyncio

from fastapi import FastAPI

from code_factory.app import create_app
from code_factory.platform.config import Settings


async def test_the_app_lifespan_owns_the_tasks_and_cancels_them_on_shutdown(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> None:
    app = create_app(settings, guarded=False)
    started = asyncio.Event()

    async def forever() -> None:
        started.set()
        await asyncio.Event().wait()

    async with app.router.lifespan_context(app):
        task = app.state.tasks.start("probe", forever)
        await started.wait()
        assert not task.done()
    assert task.cancelled()


async def test_the_app_fixture_starts_no_module_background_task(app: FastAPI) -> None:
    # A background task works on the one connection the fixture's sessions share, or spawns a
    # process, at an interval the test does not control: under load a test outlasts the interval
    # and the task's savepoint lands inside the test's.
    assert app.state.tasks.names == []
