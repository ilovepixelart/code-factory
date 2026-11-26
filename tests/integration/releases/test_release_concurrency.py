"""Releases under real concurrency: pooled, committed sessions, as two processes would have.

The shared fixtures run on one rolled-back connection, which cannot overlap two transactions.
These tests commit, so each works in a repository of its own name and deletes it afterwards.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine
from code_factory.platform.errors import ConflictError
from code_factory.releases.service import ReleaseService
from code_factory.tickets.service import TicketService
from ticket_values import OWNER

LOCK_WAIT_S = 5


@pytest.fixture
async def engine(settings: Settings, migrated: None) -> AsyncGenerator[AsyncEngine]:  # noqa: ARG001
    pooled = create_engine(settings)
    try:
        yield pooled
    finally:
        await pooled.dispose()


@pytest.fixture
async def repo(engine: AsyncEngine) -> AsyncGenerator[str]:
    name = f"concurrent-{uuid.uuid4().hex[:10]}"
    try:
        yield name
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("delete from releases where repository = :name"), {"name": name}
            )


@pytest.fixture
def releases(engine: AsyncEngine) -> ReleaseService:
    uow = UnitOfWork(async_sessionmaker(engine, expire_on_commit=False))
    return ReleaseService(uow, TicketService(uow))


async def test_two_drafts_of_one_version_give_one_release_and_one_conflict(
    releases: ReleaseService, repo: str, engine: AsyncEngine
) -> None:
    outcomes = await asyncio.gather(
        releases.draft(repo, "1.0.0", by=OWNER),
        releases.draft(repo, "1.0.0", by=OWNER),
        return_exceptions=True,
    )
    assert sorted(type(outcome).__name__ for outcome in outcomes) == [
        "ConflictError",
        "ReleaseView",
    ]
    assert any(isinstance(outcome, ConflictError) for outcome in outcomes)
    async with engine.connect() as connection:
        count = await connection.scalar(
            text("select count(*) from releases where repository = :name"), {"name": repo}
        )
    assert count == 1


async def _publish_waits_for(engine: AsyncEngine) -> None:
    """Return once a statement on the repository's release is blocked on a row lock."""
    async with asyncio.timeout(LOCK_WAIT_S):
        while True:
            async with engine.connect() as connection:
                blocked = await connection.scalar(
                    text(
                        "select count(*) from pg_stat_activity "
                        "where wait_event_type = 'Lock' and query ilike '%releases%'"
                    )
                )
            if blocked:
                return
            await asyncio.sleep(0.02)


async def test_publish_names_the_tickets_of_notes_edited_while_it_waited(
    releases: ReleaseService, repo: str, engine: AsyncEngine
) -> None:
    await releases.draft(repo, "1.0.0", by=OWNER)
    async with engine.connect() as editor:
        await editor.execute(
            text("update releases set notes = 'Names CF-7.' where repository = :name"),
            {"name": repo},
        )  # the edit is open: its row lock is held and its notes are not yet visible
        publishing = asyncio.create_task(releases.publish(repo, "1.0.0", by=OWNER))
        try:
            await _publish_waits_for(engine)
        finally:
            await editor.commit()
    published = await publishing
    assert published.notes == "Names CF-7."
    assert published.tickets == ["CF-7"]
