"""Startup and shutdown of the HTTP app, on the runtime every entry point shares."""

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI

from code_factory.platform.module import Module, Resources
from code_factory.platform.runtime import running
from code_factory.platform.services import Services

logger = logging.getLogger(__name__)

# Lines for the person who started the server (a sign-in link), printed after `serving on`.
type StartupLines = Callable[[], Awaitable[list[str]]]


@asynccontextmanager
async def app_lifespan(
    app: FastAPI,
    *,
    resources: Resources,
    services: Services,
    modules: Sequence[Module],
    startup_lines: StartupLines | None = None,
) -> AsyncGenerator[None]:
    """Run `platform.runtime.running` for the life of the app and publish what it owns.

    Each module's `background` runs once the schema is checked and tasks are accepted.
    """
    async with running(resources) as tasks:
        app.state.engine = resources.engine
        app.state.tasks = tasks
        for module in modules:
            if module.background is not None:
                module.background(services, tasks)
        app.state.startup_lines = await startup_lines() if startup_lines is not None else []
        logger.info("started", extra={"database": resources.settings.database_target})
        yield
        logger.info("stopping")
