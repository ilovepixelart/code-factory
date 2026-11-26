"""What the push tables guarantee when two passes race."""

from datetime import UTC, datetime

from code_factory.platform.db import UnitOfWork
from code_factory.push.models import Kept
from code_factory.push.repository import PushRepository

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


async def test_a_digest_is_claimed_by_one_pass_only(uow: UnitOfWork) -> None:
    async with uow() as session:
        first = await PushRepository(session).claim("d1", NOW)
    async with uow() as session:
        second = await PushRepository(session).claim("d1", NOW)
    assert (first, second) == (True, False)


async def test_a_token_is_spent_once(uow: UnitOfWork) -> None:
    async with uow() as session:
        await PushRepository(session).mint("t1", Kept("req1", (), NOW.timestamp()), NOW)
    async with uow() as session:
        first = await PushRepository(session).spend("t1")
    async with uow() as session:
        second = await PushRepository(session).spend("t1")
    assert (first, second) == (Kept("req1", (), NOW.timestamp()), None)


async def test_a_new_token_for_a_request_replaces_the_old_one(uow: UnitOfWork) -> None:
    async with uow() as session:
        await PushRepository(session).mint("t1", Kept("req1", (), NOW.timestamp()), NOW)
        await PushRepository(session).mint("t2", Kept("req1", (), NOW.timestamp()), NOW)
    async with uow() as session:
        found = (await PushRepository(session).find("t1"), await PushRepository(session).find("t2"))
    assert found == (None, Kept("req1", (), NOW.timestamp()))
