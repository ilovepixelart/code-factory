"""`CODE_FACTORY_DB_SCHEMA`: one database holds isolated copies of the application tables."""

import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from code_factory.platform.config import Settings
from code_factory.platform.db import create_engine
from code_factory.platform.db.migrate import upgrade


@pytest.fixture
async def schema(settings: Settings, migrated: None) -> AsyncGenerator[str]:  # noqa: ARG001
    name = f"e2e_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(settings.database_url.get_secret_value())
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{name}"'))
    try:
        yield name
    finally:
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
        await admin.dispose()


async def test_the_engine_resolves_unqualified_names_in_the_configured_schema(
    settings: Settings, schema: str
) -> None:
    engine = create_engine(settings.model_copy(update={"db_schema": schema}))
    try:
        async with engine.connect() as connection:
            found = (await connection.execute(text("SHOW search_path"))).scalar_one()
    finally:
        await engine.dispose()
    assert found == schema


async def test_migrating_with_a_schema_builds_the_tables_there_and_leaves_public_alone(
    settings: Settings, schema: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODE_FACTORY_DB_SCHEMA", schema)
    await asyncio.to_thread(upgrade)
    admin = create_async_engine(settings.database_url.get_secret_value())
    try:
        async with admin.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :s AND table_name IN ('schema_info', 'alembic_version')"
                ),
                {"s": schema},
            )
            names = sorted(row[0] for row in rows)
    finally:
        await admin.dispose()
    assert names == ["alembic_version", "schema_info"]
