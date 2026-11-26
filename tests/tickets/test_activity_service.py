"""A ticket's history: appended in order, never changed, read in pages.

Records are shaped as the previous implementation's activity goldens hold them (`created` with
`type`, `stage` with `from` and `to`, `attempts_judged` with a list of objects).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.tickets.models import NewActivity, Ticket
from code_factory.tickets.service import ActivityService
from ticket_values import NOW, OWNER

AT = datetime(2026, 10, 4, 10, 1, tzinfo=UTC)
JUDGED = {"winner": 2, "attempts": [{"attempt": 1, "passed": True, "lines": 10, "cost": 0.5}]}


async def test_records_read_back_in_the_order_they_were_appended(
    activity: ActivityService, ticket: Ticket
) -> None:
    await activity.append(
        ticket.id,
        NewActivity(kind="stage", data={"from": "spec", "to": "build"}, at=AT),
        by="run-1",
    )
    await activity.append(ticket.id, NewActivity(kind="attempts_judged", data=JUDGED), by=OWNER)
    page = await activity.list_activity(ticket.id)
    assert [(r.kind, r.by, r.at, r.data) for r in page.items] == [
        ("created", OWNER, NOW, {"type": "feature"}),
        ("stage", "run-1", AT, {"from": "spec", "to": "build"}),
        ("attempts_judged", OWNER, NOW, JUDGED),
    ]
    assert page.next_cursor is None


async def test_history_is_read_in_pages_newest_first_and_by_kind(
    activity: ActivityService, ticket: Ticket
) -> None:
    for word in ("one", "two", "three"):
        await activity.record_note(ticket.id, word, "note", by=OWNER)
    first = await activity.list_activity(ticket.id, kinds=["note"], limit=2, newest_first=True)
    assert [r.data["text"] for r in first.items] == ["three", "two"]
    assert first.next_cursor is not None
    rest = await activity.list_activity(
        ticket.id, kinds=["note"], limit=2, cursor=first.next_cursor, newest_first=True
    )
    assert [r.data["text"] for r in rest.items] == ["one"]
    assert rest.next_cursor is None


async def test_a_note_must_say_something_within_its_limit(
    activity: ActivityService, ticket: Ticket
) -> None:
    with pytest.raises(BadRequestError, match="a note needs text"):
        await activity.record_note(ticket.id, "  ", "note", by=OWNER)
    with pytest.raises(BadRequestError, match="a note is at most 4000 characters"):
        await activity.record_note(ticket.id, "x" * 4001, "note", by=OWNER)
    taken = await activity.record_note(ticket.id, "x" * 4000, "diagnosis", by=OWNER)
    assert (taken.kind, len(taken.data["text"])) == ("diagnosis", 4000)


async def test_what_an_actor_wrote_is_counted_by_kind(
    activity: ActivityService, ticket: Ticket
) -> None:
    before = await activity.count_authored("run-counted", "note")
    await activity.record_note(ticket.id, "a", "note", by="run-counted")
    await activity.record_note(ticket.id, "b", "note", by="run-counted")
    await activity.record_note(ticket.id, "c", "note", by="someone-else")
    assert await activity.count_authored("run-counted", "note") == before + 2


@pytest.mark.parametrize("kind", ["", "Stage", "stage move", "1st", "stage-move"])
async def test_a_record_kind_is_one_lower_case_word(
    activity: ActivityService, ticket: Ticket, kind: str
) -> None:
    with pytest.raises(BadRequestError, match="is not a record kind"):
        await activity.append(ticket.id, NewActivity(kind=kind), by=OWNER)


async def test_the_history_of_an_unknown_ticket_is_not_found(activity: ActivityService) -> None:
    with pytest.raises(NotFoundError, match="CF-999999 does not exist"):
        await activity.append("CF-999999", NewActivity(kind="note"), by=OWNER)
    with pytest.raises(NotFoundError, match="CF-999999 does not exist"):
        await activity.list_activity("CF-999999")


@pytest.mark.usefixtures("ticket")  # its `created` record is a row for the row trigger to guard
async def test_a_record_cannot_be_changed_or_removed(db_session: AsyncSession) -> None:
    for statement in (
        "update ticket_activity set kind = 'forged'",
        "delete from ticket_activity",
        "truncate ticket_activity",
    ):
        with pytest.raises(DBAPIError, match="ticket_activity is append-only"):
            async with db_session.begin_nested():
                await db_session.execute(text(statement))
