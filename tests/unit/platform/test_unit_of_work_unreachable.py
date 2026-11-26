"""A database that cannot be reached is a 503 with a sentence, not an internal error."""

import pytest
from sqlalchemy import text

from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine, create_session_factory
from code_factory.platform.errors import DatabaseUnavailableError


async def test_a_unit_of_work_over_an_unreachable_database_says_so(
    offline_settings: Settings,
) -> None:
    engine = create_engine(offline_settings)
    uow = UnitOfWork(create_session_factory(engine))
    try:
        unit = uow()
        statement = text("select 1")
        with pytest.raises(DatabaseUnavailableError, match=r"^the database is not reachable"):
            async with unit as session:
                await session.execute(statement)
    finally:
        await engine.dispose()


async def test_an_error_that_is_not_the_connection_passes_through(
    offline_settings: Settings,
) -> None:
    engine = create_engine(offline_settings)
    uow = UnitOfWork(create_session_factory(engine))
    try:
        unit = uow()
        with pytest.raises(FileNotFoundError):
            async with unit:
                raise FileNotFoundError("the agent file is gone")
    finally:
        await engine.dispose()
