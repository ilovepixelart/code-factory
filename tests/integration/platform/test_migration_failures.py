"""`code-factory db upgrade` answers its two expected failures with a sentence, not a traceback."""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from code_factory.platform.config import Settings
from code_factory.platform.db import EXPECTED_REVISION, create_engine
from code_factory.platform.db import migrate as migrate_module
from code_factory.platform.db.migrate import alembic_config, upgrade
from code_factory.platform.errors import (
    DatabaseBusyError,
    DatabaseUnavailableError,
    SchemaMismatchError,
)

SCHEMA_INFO_REVISION = "2fdc42b35fd5"  # the revision before the seed, whatever follows it


@pytest.fixture
async def engine(settings: Settings, migrated: None) -> AsyncGenerator[AsyncEngine]:  # noqa: ARG001
    engine = create_engine(settings)
    try:
        yield engine
    finally:
        await engine.dispose()
        await asyncio.to_thread(command.upgrade, alembic_config(), "head")


async def test_a_migration_that_cannot_take_its_lock_says_who_to_wait_for(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(migrate_module, "LOCK_TIMEOUT_MS", 500)
    await asyncio.to_thread(
        command.downgrade, alembic_config(), SCHEMA_INFO_REVISION
    )  # head re-inserts the row
    async with engine.connect() as holder:
        await holder.execute(text("lock table schema_info in access exclusive mode"))
        with pytest.raises(DatabaseBusyError) as raised:
            await asyncio.to_thread(upgrade)
        await holder.rollback()
    assert str(raised.value) == (
        "the migration could not take a lock within 0.5 s: another session holds a lock on the "
        "database (a running migration or a long query); retry when it has finished"
    )


async def test_a_database_at_a_revision_this_build_does_not_know_is_refused_with_a_sentence(
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("update alembic_version set version_num = 'ffffffffffff'"))
    try:
        with pytest.raises(SchemaMismatchError) as raised:
            await asyncio.to_thread(upgrade)
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("update alembic_version set version_num = :head"), {"head": EXPECTED_REVISION}
            )
    assert str(raised.value) == (
        "the database is at revision ffffffffffff, which this build does not know; install the "
        "build that wrote the database, or restore it from a backup"
    )


class _Failure(Exception):  # noqa: N818  # stands in for the driver's error: only its SQLSTATE is read
    def __init__(self, sqlstate: str) -> None:
        super().__init__("driver text that must not be printed")
        self.sqlstate = sqlstate


def _fail_with(monkeypatch: pytest.MonkeyPatch, sqlstate: str) -> None:
    def upgrade_that_fails(_config: object, _revision: str) -> None:
        raise DBAPIError("alter table x", {}, _Failure(sqlstate))

    monkeypatch.setattr(migrate_module.command, "upgrade", upgrade_that_fails)


def test_a_statement_over_the_timeout_says_it_was_cancelled(
    settings: Settings,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fail_with(monkeypatch, "57014")
    with pytest.raises(DatabaseBusyError) as raised:
        upgrade()
    assert str(raised.value) == (
        "a migration statement ran longer than 300 s and was cancelled; "
        "see docs/architecture.md (Migrations) for long statements"
    )


def test_any_other_database_error_still_reads_as_not_reachable(
    settings: Settings,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fail_with(monkeypatch, "08006")
    with pytest.raises(DatabaseUnavailableError, match="is not reachable"):
        upgrade()
