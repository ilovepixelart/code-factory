"""The app's lifespan run by one task for a test, and the schema variable a worker sets.

A module of its own, not `conftest`: several `conftest.py` files exist, so importing a name from
`conftest` reaches whichever one Python loaded first.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace

from fastapi import FastAPI

from code_factory.app import MODULES

DB_SCHEMA_VARIABLE = "CODE_FACTORY_DB_SCHEMA"
# The modules without their background tasks: one works on the connection the sessions share, or
# spawns a process, at an interval the test does not control, so a test that outlasts the interval
# under load has the task's savepoint land inside its own. A test of a task builds it itself.
IDLE_MODULES = tuple(replace(module, background=None) for module in MODULES)


@asynccontextmanager
async def running_lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Run the app's lifespan in its own task, entered and exited by that one task.

    ASGITransport does not run the lifespan. Entering it in a fixture's setup and leaving it in its
    teardown would happen in two different tasks, which AnyIO's cancel scopes (inside the MCP
    session manager) refuse; a holder task keeps both ends in one.
    """
    started = asyncio.Event()
    stop = asyncio.Event()

    async def hold() -> None:
        async with app.router.lifespan_context(app):
            started.set()
            await stop.wait()

    holder = asyncio.create_task(hold())
    waiter = asyncio.create_task(started.wait())
    await asyncio.wait({holder, waiter}, return_when=asyncio.FIRST_COMPLETED)
    waiter.cancel()
    if holder.done():
        holder.result()  # startup failed: raise why
    try:
        yield
    finally:
        stop.set()
        await holder
