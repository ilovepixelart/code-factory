"""Fixtures of the talk tests."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.db import UnitOfWork
from code_factory.talk.service import TalkService
from talk_values import Clock


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def talk(uow: UnitOfWork, clock: Clock) -> TalkService:
    """The talk service on the isolated connection, on the test's clock."""
    return TalkService(uow, clock=clock)


@pytest.fixture
async def bare_ticket(db_session: AsyncSession) -> str:
    """A ticket row with no history, so a test may delete it."""
    number = await db_session.scalar(
        text("insert into tickets (repository, title) values ('sample', 'Bare') returning number")
    )
    return f"CF-{number}"
