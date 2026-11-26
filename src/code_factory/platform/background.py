"""Background work owned by the application lifespan.

Every task lives in one `asyncio.TaskGroup`, which keeps a strong reference to it (the event loop
holds only weak ones) and is awaited before the lifespan ends. Leaving the block cancels what is
still running; a task that fails is logged and does not take its siblings or the app down.

A `BackgroundTasks` exists from the moment the resources are built, so a service can hold it, but
it starts work only between `run()` entering and leaving (`platform.runtime.running`).
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)


class BackgroundTasks:
    """Starts named tasks inside the owning task group."""

    def __init__(self) -> None:
        self._group: asyncio.TaskGroup | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def names(self) -> list[str]:
        """Names of the tasks that are still running."""
        return [name for name, task in self._tasks.items() if not task.done()]

    def start(self, name: str, work: Callable[[], Coroutine[Any, Any, None]]) -> asyncio.Task[None]:
        """Run `work()` as a task named `name`.

        A loop that must survive one failed pass catches inside itself; an exception that reaches
        here ends only this task and is logged. A name identifies a task for `names` and
        shutdown, so starting one whose task still runs raises `ValueError`.
        """
        if self._group is None:
            msg = f"cannot start background task {name}: the application is not running"
            raise RuntimeError(msg)
        if name in self.names:
            msg = f"background task {name} is already running"
            raise ValueError(msg)
        task = self._group.create_task(self._supervise(name, work), name=name)
        self._tasks[name] = task
        return task

    def cancel_all(self) -> None:
        """Ask every running task to stop."""
        for task in self._tasks.values():
            task.cancel()

    @asynccontextmanager
    async def run(self) -> AsyncGenerator[None]:
        """Accept tasks inside the block; on exit cancel them and wait until they have finished."""
        async with asyncio.TaskGroup() as group:
            self._group = group
            try:
                yield
            finally:
                self.cancel_all()
                self._group = None

    @staticmethod
    async def _supervise(name: str, work: Callable[[], Coroutine[Any, Any, None]]) -> None:
        try:
            await work()
        except Exception:
            logger.exception("background task %s failed", name)


@asynccontextmanager
async def background_tasks() -> AsyncGenerator[BackgroundTasks]:
    """Yield a running registry of its own, for code that has no `Resources`."""
    tasks = BackgroundTasks()
    async with tasks.run():
        yield tasks
