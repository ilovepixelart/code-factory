"""The startup check: the app never migrates, it reads the state and refuses what it cannot read."""

import time

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app_lifespan import running_lifespan
from code_factory.app import create_app
from code_factory.platform.config import Settings
from code_factory.platform.db import (
    EXPECTED_REVISION,
    SchemaState,
    check_database,
    create_engine,
    read_schema_state,
)
from code_factory.platform.db import schema as schema_module
from code_factory.platform.errors import (
    DatabaseBusyError,
    SchemaMismatchError,
)


async def test_the_migrated_database_reads_as_the_head_revision_and_format_one(
    db_session: AsyncSession,
) -> None:
    state = await read_schema_state(db_session)
    assert state.revision == EXPECTED_REVISION
    assert state.data_format == 1


async def test_a_database_without_a_schema_reads_as_empty(db_session: AsyncSession) -> None:
    # Postgres DDL is transactional: the test's outer transaction undoes both drops.
    await db_session.execute(text("drop table alembic_version"))
    await db_session.execute(text("drop table schema_info"))
    assert await read_schema_state(db_session) == SchemaState(revision=None, data_format=None)


@pytest.mark.parametrize(
    ("patched_format", "message"),
    [
        (2, "the database data format is 1 but this build reads 2; run `code-factory db upgrade`"),
        (0, "the database data format is 1 but this build reads 0; install a newer code-factory"),
    ],
)
async def test_the_app_refuses_to_start_on_a_data_format_it_cannot_read(
    settings: Settings,
    migrated: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    patched_format: int,
    message: str,
) -> None:
    monkeypatch.setattr(schema_module, "DATA_FORMAT_VERSION", patched_format)
    lifespan = running_lifespan(create_app(settings, guarded=False))
    with pytest.raises(SchemaMismatchError) as raised:
        async with lifespan:
            pytest.fail("the app started on a database it cannot read")
    assert str(raised.value) == message


async def test_the_app_does_not_migrate_a_database_that_is_behind(
    settings: Settings,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(schema_module, "EXPECTED_REVISION", "a_newer_revision")
    lifespan = running_lifespan(create_app(settings, guarded=False))
    with pytest.raises(SchemaMismatchError, match="code-factory db upgrade"):
        async with lifespan:
            pytest.fail("the app started on a database that is behind")
    assert (await read_schema_state(db_session)).revision == EXPECTED_REVISION


async def test_a_busy_database_fails_the_check_within_its_deadline_and_says_so(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> None:
    """A migration holds an exclusive lock on schema_info: the check must not wait for it."""
    engine = create_engine(settings)
    quick = settings.model_copy(update={"schema_check_timeout_s": 0.5})
    try:
        async with engine.connect() as holder:
            await holder.execute(text("lock table schema_info in access exclusive mode"))
            started = time.monotonic()
            with pytest.raises(DatabaseBusyError) as raised:
                await check_database(quick)
            elapsed = time.monotonic() - started
            await holder.rollback()
    finally:
        await engine.dispose()
    assert elapsed < 3
    assert str(raised.value) == (
        "the database did not answer the schema check within 0.5 s: it is busy, for example "
        "while a migration runs; retry in a moment"
    )
