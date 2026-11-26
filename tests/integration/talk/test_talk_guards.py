"""Id bounds, first-answer time, status under a racing answer and bounded lock waits."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from test_talk_questions import ask, committed_ticket

from code_factory.platform.config import Settings
from code_factory.platform.db import create_engine, create_session_factory, lock_until_commit
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.talk import repository
from code_factory.talk.models import Reply
from code_factory.talk.service import TalkService
from code_factory.tickets.models import Ticket
from talk_values import OWNER, Clock

BIGINT_END = 2**63


@pytest.mark.parametrize(
    "bad", ["CF-9223372036854775808", "CF-99999999999999999999", "CF-" + "9" * 5000]
)
async def test_a_ticket_number_past_the_database_range_is_a_bad_request(
    talk: TalkService, bad: str
) -> None:
    with pytest.raises(BadRequestError, match=r"is not a ticket id CF-<n>"):
        await talk.open_counts([bad])
    with pytest.raises(BadRequestError, match=r"is not a ticket id CF-<n>"):
        await talk.ask(bad, "Which?", [], by=OWNER)


async def test_the_largest_ticket_number_in_range_is_an_unknown_ticket(talk: TalkService) -> None:
    with pytest.raises(NotFoundError, match=r"^CF-9223372036854775807 does not exist"):
        await talk.add_comment("CF-9223372036854775807", "hi", OWNER)


async def test_a_question_id_past_the_database_range_is_no_question(talk: TalkService) -> None:
    calls = (
        lambda: talk.get(BIGINT_END),
        lambda: talk.answer(BIGINT_END, Reply(text="x"), by=OWNER, channel="http"),
        lambda: talk.withdraw(BIGINT_END, by=OWNER),
    )
    for call in calls:
        with pytest.raises(NotFoundError, match=rf"^no question {BIGINT_END}$"):
            await call()


async def test_a_replaced_answer_keeps_the_time_of_the_first(
    talk: TalkService, ticket: Ticket, clock: Clock, db_session: AsyncSession
) -> None:
    asked = await ask(talk, ticket.id)
    first = clock.now
    await talk.answer(asked.question_id, Reply(text="blue"), by=OWNER, channel="http")
    clock.advance(minutes=5)
    await talk.answer(
        asked.question_id, Reply(text="green"), replace=True, by=OWNER, channel="http"
    )
    stored = await db_session.scalar(
        text("select answered_at from talk_questions where id = :id"), {"id": asked.question_id}
    )
    assert stored == first


async def test_a_write_waits_for_the_ticket_lock_and_gives_up_with_a_conflict(
    settings: Settings,
    migrated: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(repository, "LOCK_TIMEOUT_MS", 300)
    async with committed_ticket(settings) as (service, ticket):
        number = int(ticket.removeprefix("CF-"))
        holder_engine = create_engine(settings)
        try:
            async with create_session_factory(holder_engine)() as holder:
                await lock_until_commit(holder, f"{repository.LOCK_KEY}:{number}")
                writes = (
                    lambda: service.add_comment(ticket, "hi", OWNER),
                    lambda: service.post_message(ticket, "hi", OWNER, "run"),
                    lambda: ask(service, ticket),
                )
                for write in writes:
                    given = write()
                    with pytest.raises(
                        ConflictError, match=r"^another change to the same ticket is in"
                    ):
                        await asyncio.wait_for(given, timeout=5)
                await holder.rollback()
            await service.add_comment(ticket, "now", OWNER)
        finally:
            await holder_engine.dispose()
