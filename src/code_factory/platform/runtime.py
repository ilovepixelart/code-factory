"""What runs between startup and shutdown, shared by every way of running the application.

The HTTP app, the stdio MCP server and CLI commands that use services all enter `running`, so
each one checks the schema before it serves, owns background tasks, and disposes the engine.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from code_factory.platform.background import BackgroundTasks
from code_factory.platform.db import check_engine
from code_factory.platform.module import Resources

logger = logging.getLogger(__name__)


async def run_on_stop(resources: Resources) -> None:
    """Run the stop signals, then the `on_stop` hooks, in order; a failing one is only logged."""
    for signal in resources.on_stopping:
        try:
            signal()
        except Exception:
            logger.exception(
                "on_stopping signal %s failed", getattr(signal, "__name__", repr(signal))
            )
    for hook in resources.on_stop:
        try:
            await hook()
        except Exception:
            logger.exception("on_stop hook %s failed", getattr(hook, "__name__", repr(hook)))


@asynccontextmanager
async def running(resources: Resources) -> AsyncGenerator[BackgroundTasks]:
    """Refuse a database this build cannot read, then accept background tasks.

    The schema is checked, never migrated: `code-factory db upgrade` is the one way to migrate.
    The `on_stop` hooks run when the block ends, before the tasks are cancelled. The engine is
    disposed when the block ends, however it ends.
    """
    try:
        await check_engine(resources.engine, resources.settings)
        async with resources.tasks.run():
            try:
                yield resources.tasks
            finally:
                await run_on_stop(resources)
    finally:
        await resources.engine.dispose()
