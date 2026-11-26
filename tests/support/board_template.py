"""The `board` sample, loaded once per session and copied into each test that asks for it.

`SampleService.load("board")` costs about 1.5 s; the route tests that need that state take
`board_ids` instead, which copies the rows of a template schema into the test's own transaction.
"""

import asyncio
import os
import uuid
from collections.abc import Iterator
from typing import NamedTuple

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app_lifespan import DB_SCHEMA_VARIABLE, running_lifespan
from code_factory.app import create_app
from code_factory.platform.config import Settings
from code_factory.platform.db import Base, SchemaInfo, create_engine, create_schema, drop_schema
from code_factory.platform.db.migrate import upgrade
from code_factory.sample.service import SampleService


class BoardTemplate(NamedTuple):
    """The `board` sample loaded once: its schema, ticket ids by title, tables and sequences."""

    schema: str
    ids: dict[str, str]
    tables: list[str]
    sequences: dict[str, int]


def _load_board_template(settings: Settings) -> BoardTemplate:
    """Migrate `settings.db_schema`, load the `board` sample into it and record what it filled."""
    asyncio.run(drop_schema(settings))
    asyncio.run(create_schema(settings))
    previous = os.environ.get(DB_SCHEMA_VARIABLE)
    os.environ[DB_SCHEMA_VARIABLE] = settings.db_schema
    try:
        upgrade()
    finally:
        if previous is None:
            del os.environ[DB_SCHEMA_VARIABLE]
        else:
            os.environ[DB_SCHEMA_VARIABLE] = previous

    async def load() -> BoardTemplate:
        application = create_app(settings, guarded=False)
        async with running_lifespan(application):
            ids = await application.state.services.get(SampleService).load("board")
        engine = create_engine(settings)
        try:
            async with engine.connect() as probe:
                tables = [
                    table.name
                    for table in Base.metadata.sorted_tables
                    if table.name != SchemaInfo.__tablename__  # seeded by its migration
                    and (await probe.execute(select(table).limit(1))).first() is not None
                ]
                rows = await probe.execute(
                    text(
                        "SELECT sequencename, last_value FROM pg_sequences "
                        "WHERE schemaname = :schema AND last_value IS NOT NULL"
                    ),
                    {"schema": settings.db_schema},
                )
                sequences = dict(rows.all())
        finally:
            await engine.dispose()
        return BoardTemplate(settings.db_schema, ids, tables, sequences)

    return asyncio.run(load())


@pytest.fixture(scope="session")
def board_template(settings: Settings, migrated: None) -> Iterator[BoardTemplate]:  # noqa: ARG001
    """The `board` sample loaded once per session into a schema of its own."""
    # Under xdist the name carries the run id, so the controller's cleanup finds it too.
    name = (
        f"{settings.db_schema}_tpl"
        if "PYTEST_XDIST_WORKER" in os.environ
        else f"board_template_{uuid.uuid4().hex[:10]}"
    )
    template = settings.model_copy(update={"db_schema": name})
    try:
        yield _load_board_template(template)
    finally:
        asyncio.run(drop_schema(template))


@pytest.fixture
async def board_ids(connection: AsyncConnection, board_template: BoardTemplate) -> dict[str, str]:
    """The `board` sample in the test's schema, ticket id by title.

    The rows are copied from the template, so the test starts from the state `SampleService.load`
    leaves, without running it again; the test's transaction rolls them back as any other write.
    """
    for name in board_template.tables:
        await connection.execute(
            text(
                f'INSERT INTO "{name}" OVERRIDING SYSTEM VALUE '  # noqa: S608  # names from our metadata'
                f'SELECT * FROM "{board_template.schema}"."{name}"'
            )
        )
    # Ticket numbers and identity columns draw from sequences the copy did not advance, and a
    # sequence never rolls back: move each to the template's value (never backwards), so a row the
    # test inserts cannot take the id of a copied one.
    for sequence, value in board_template.sequences.items():
        await connection.execute(
            text(
                "SELECT setval(CAST(CAST(:sequence AS text) AS regclass), "
                "GREATEST(CAST(:value AS bigint), "
                "(SELECT coalesce(max(last_value), 1) FROM pg_sequences "
                "WHERE schemaname = current_schema() AND sequencename = CAST(:sequence AS text))))"
            ),
            {"sequence": sequence, "value": value},
        )
    return dict(board_template.ids)
