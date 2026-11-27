"""What this build expects of the database, and the startup check that enforces it.

The application never migrates by itself. It reads the Alembic revision and the data format
version and refuses to run on anything else, naming the command that repairs it.
"""

import asyncio
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from code_factory.platform.config import Settings
from code_factory.platform.db.engine import (
    DATABASE_ERRORS,
    create_engine,
    create_session_factory,
    unavailable,
)
from code_factory.platform.errors import DatabaseBusyError, SchemaMismatchError

# The head revision of `alembic/versions`; a test fails when it drifts from the script directory.
EXPECTED_REVISION = "a65e20cf7c84"
# The data format this build reads and writes. A migration that changes a persisted format raises
# it in the same revision (`schema_info.data_format_version`) and this constant with it.
DATA_FORMAT_VERSION = 1

_UPGRADE = "run `code-factory db upgrade`"


@dataclass(frozen=True)
class SchemaState:
    """What the database says about itself; `None` where it says nothing yet."""

    revision: str | None
    data_format: int | None


async def read_schema_state(session: AsyncSession) -> SchemaState:
    """Read the Alembic revision and the data format version, tolerating an empty database."""
    has_revision_table = await session.scalar(
        text("select to_regclass('alembic_version') is not null")
    )
    revision = None
    if has_revision_table:
        revision = await session.scalar(text("select version_num from alembic_version"))
    has_info = await session.scalar(text("select to_regclass('schema_info') is not null"))
    data_format = None
    if has_info:
        data_format = await session.scalar(
            text("select data_format_version from schema_info where id = 1")
        )
    return SchemaState(revision=revision, data_format=data_format)


def verify_schema(state: SchemaState) -> None:
    """Raise `SchemaMismatchError` with the repair when the state is not the one expected."""
    if state.revision is None:
        msg = f"the database has no schema yet; {_UPGRADE}"
        raise SchemaMismatchError(msg)
    if state.revision != EXPECTED_REVISION:
        msg = (
            f"the database is at revision {state.revision} but this build expects "
            f"{EXPECTED_REVISION}; {_UPGRADE}, or install the build that wrote the database "
            "if it is newer"
        )
        raise SchemaMismatchError(msg)
    if state.data_format is None:
        msg = f"schema_info holds no data format version; {_UPGRADE}"
        raise SchemaMismatchError(msg)
    if state.data_format > DATA_FORMAT_VERSION:
        msg = (
            f"the database data format is {state.data_format} but this build reads "
            f"{DATA_FORMAT_VERSION}; install a newer code-factory"
        )
        raise SchemaMismatchError(msg)
    if state.data_format < DATA_FORMAT_VERSION:
        msg = (
            f"the database data format is {state.data_format} but this build reads "
            f"{DATA_FORMAT_VERSION}; {_UPGRADE}"
        )
        raise SchemaMismatchError(msg)


def _check_timed_out(settings: Settings) -> DatabaseBusyError:
    msg = (
        f"the database did not answer the schema check within "
        f"{settings.schema_check_timeout_s:g} s: it is busy, for example while a migration "
        "runs; retry in a moment"
    )
    return DatabaseBusyError(msg)


async def check_engine(engine: AsyncEngine, settings: Settings) -> SchemaState:
    """Read the state through `engine` and verify it.

    An unreachable server raises `DatabaseUnavailableError`; a state this build cannot read
    raises `SchemaMismatchError`. The whole read is bounded by `schema_check_timeout_s`: a lock
    held on `schema_info` (a migration running) raises `DatabaseBusyError` instead of waiting.
    """
    try:
        async with asyncio.timeout(settings.schema_check_timeout_s):
            state = await _read_state(engine, settings)
    except TimeoutError:
        raise _check_timed_out(settings) from None
    verify_schema(state)
    return state


async def _read_state(engine: AsyncEngine, settings: Settings) -> SchemaState:
    try:
        async with create_session_factory(engine)() as session:
            return await read_schema_state(session)
    except DATABASE_ERRORS as error:
        raise unavailable(settings, error) from error


async def check_database(settings: Settings) -> SchemaState:
    """`check_engine` with a fresh engine that is disposed again."""
    engine = create_engine(settings)
    try:
        return await check_engine(engine, settings)
    finally:
        await engine.dispose()
