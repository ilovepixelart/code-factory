"""Two requests for one token, on separate connections that really commit."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text

from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine, create_session_factory
from code_factory.platform.errors import GoneError
from code_factory.undo.service import UndoService

# The window is read from the clock: a real one would let a loaded machine outlast the window
# between the offer and the claims, and no handler would run.
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


@pytest.fixture
async def committed(settings: Settings, migrated: None) -> AsyncGenerator[UndoService]:  # noqa: ARG001
    engine = create_engine(settings)
    service = UndoService(UnitOfWork(create_session_factory(engine)), clock=lambda: NOW)
    try:
        yield service
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM undo_entries WHERE kind = 'test.race'"))
        await engine.dispose()


async def test_two_simultaneous_undos_of_one_token_run_the_handler_once(
    committed: UndoService,
) -> None:
    runs: list[str] = []

    async def handler(_payload: dict[str, Any], by: str) -> None:
        await asyncio.sleep(0.05)
        runs.append(by)

    committed.register("test.race", handler)
    token = (await committed.offer("test.race", {}, "n")).undo or ""
    outcomes = await asyncio.gather(
        committed.undo(token, "first"), committed.undo(token, "second"), return_exceptions=True
    )
    gone = [o for o in outcomes if isinstance(o, GoneError)]
    assert (len(runs), len(gone)) == (1, 1)
