"""An admission check reads the store it guards, so it runs under the write it admits.

Two writers on separate connections that really commit: without a lock held from the check to the
commit, both read the store before either wrote and both are admitted.
"""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text

from code_factory.memory.models import Intake, NewMemory
from code_factory.memory.service import MemoryService
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine, create_session_factory
from code_factory.platform.errors import ConflictError
from memory_values import NOW, OWNER

REPO = "admission-race"


@pytest.fixture
async def committed(settings: Settings, migrated: None) -> AsyncGenerator[MemoryService]:  # noqa: ARG001
    engine = create_engine(settings)
    service = MemoryService(UnitOfWork(create_session_factory(engine)), clock=lambda: NOW)
    try:
        yield service
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM memory_entries WHERE repository = :r"), {"r": REPO}
            )
        await engine.dispose()


async def test_two_simultaneous_adds_cannot_both_pass_a_check_of_the_store(
    committed: MemoryService,
) -> None:
    async def admit(draft: NewMemory, intake: Intake) -> None:  # noqa: ARG001
        held = len(await committed.list_entries(REPO))
        await asyncio.sleep(0.2)
        if held >= 1:
            raise ConflictError("the store is full")

    committed.add_admission(admit)
    drafts = [
        NewMemory(repository=REPO, kind="rule", statement=f"Keep it {word}", source="chat")
        for word in ("small", "short")
    ]
    outcomes = await asyncio.gather(
        *(committed.add(draft, by=OWNER) for draft in drafts), return_exceptions=True
    )
    refused = [o for o in outcomes if isinstance(o, ConflictError)]
    assert (len(refused), len(await committed.list_entries(REPO))) == (1, 1)
