"""Advisory locks are keyed per schema: one name blocks within a schema and never across two."""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from code_factory.platform.config import Settings
from code_factory.platform.db import create_engine, lock_key


@pytest.fixture
async def engine(settings: Settings, migrated: None) -> AsyncGenerator[AsyncEngine]:  # noqa: ARG001
    made = create_engine(settings)
    yield made
    await made.dispose()


async def _in(connection: AsyncConnection, schema: str) -> None:
    await connection.execute(select(func.set_config("search_path", schema, True)))


async def _try(connection: AsyncConnection, name: str) -> bool:
    return bool(await connection.scalar(select(func.pg_try_advisory_xact_lock(lock_key(name)))))


async def test_a_lock_blocks_its_own_schema_and_no_other(
    engine: AsyncEngine, settings: Settings
) -> None:
    async with engine.connect() as holder, engine.connect() as same, engine.connect() as other:
        await holder.begin()
        await same.begin()
        await other.begin()
        await _in(holder, settings.db_schema)
        await _in(same, settings.db_schema)
        await _in(other, f"{settings.db_schema}_other")

        held = await _try(holder, "tickets:sample")
        blocked = await _try(same, "tickets:sample")
        elsewhere = await _try(other, "tickets:sample")

    assert (held, blocked, elsewhere) == (True, False, True)


async def test_a_schema_that_does_not_exist_still_takes_a_lock(engine: AsyncEngine) -> None:
    async with engine.connect() as first, engine.connect() as second:
        await first.begin()
        await second.begin()
        for connection in (first, second):
            await _in(connection, "no_such_schema_here")

        key = await first.scalar(select(lock_key("x")))
        taken = await _try(first, "x")
        blocked = await _try(second, "x")

    assert key is not None
    assert (taken, blocked) == (True, False)
