"""Comments, messages, news and the timeline through the talk service."""

import pytest

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.talk.models import Choice, Reply
from code_factory.talk.service import TalkService
from code_factory.tickets.models import NewTicket, Ticket
from code_factory.tickets.service import TicketService
from talk_values import OWNER, RUN, START, Clock


async def test_a_comment_is_stored_with_its_author_and_place(
    talk: TalkService, ticket: Ticket
) -> None:
    await talk.add_comment(ticket.id, " Rename this ", OWNER, path="src/a.py", line=12)
    await talk.add_comment(ticket.id, "Looks good", OWNER)
    page = await talk.activity_entries(ticket.id, ["comment"])
    assert [(e.by, e.text, e.data) for e in page.items] == [
        (OWNER, "src/a.py:12: Rename this", {"path": "src/a.py", "line": 12}),
        (OWNER, "Looks good", {"path": "", "line": None}),
    ]


async def test_an_empty_comment_or_message_and_an_unknown_ticket_are_refused(
    talk: TalkService, ticket: Ticket
) -> None:
    with pytest.raises(BadRequestError, match=r"^an empty comment says nothing$"):
        await talk.add_comment(ticket.id, " ", OWNER)
    with pytest.raises(BadRequestError, match=r"^an empty message says nothing$"):
        await talk.post_message(ticket.id, " ", OWNER, "run")
    with pytest.raises(NotFoundError, match=r"^CF-99999 does not exist"):
        await talk.add_comment("CF-99999", "hi", OWNER)
    with pytest.raises(NotFoundError, match=r"^CF-99999 does not exist"):
        await talk.post_message("CF-99999", "hi", OWNER, "run")


async def test_messages_wait_until_delivered_and_delivery_is_idempotent(
    talk: TalkService, ticket: Ticket, tickets: TicketService
) -> None:
    other = await tickets.create(NewTicket(repository="sample", title="Other"), by=OWNER)
    first = await talk.post_message(ticket.id, "use files", OWNER, "next_run")
    second = await talk.post_message(ticket.id, "and tests", OWNER, "run")
    foreign = await talk.post_message(other.id, "elsewhere", OWNER, "run")
    assert [m.text for m in await talk.pending_messages(ticket.id)] == ["use files", "and tests"]
    await talk.mark_delivered(ticket.id, [first.id, foreign.id], "r-1")
    await talk.mark_delivered(ticket.id, [first.id], "r-2")
    assert [m.id for m in await talk.pending_messages(ticket.id)] == [second.id]
    assert [m.id for m in await talk.pending_messages(other.id)] == [foreign.id]
    delivered = (await talk.activity_entries(ticket.id, ["message"])).items[0]
    assert delivered.data == {"route": "next_run", "delivered": True}


async def test_news_holds_posts_and_answers_since_the_run_began_and_peek_changes_nothing(
    talk: TalkService, ticket: Ticket, clock: Clock
) -> None:
    await talk.add_comment(ticket.id, "before the run", OWNER)
    clock.advance(minutes=10)
    began = clock.now
    asked = await talk.ask(ticket.id, "Which colour?", [], by=RUN)
    clock.advance(minutes=1)
    await talk.answer(asked.question_id, Reply(text="blue"), by=OWNER, channel="http")
    clock.advance(minutes=1)
    message = await talk.post_message(ticket.id, "use files", OWNER, "run")
    news = await talk.peek_news(ticket.id, "s1", began)
    assert news is not None
    assert news.text.split("\n") == [
        f'The owner answered "Which colour?" on {ticket.id}: blue',
        (
            f"A message from the owner on {ticket.id}, sent while you work. "
            "Take it as the owner's instruction: use files"
        ),
    ]
    assert news.message_ids == [message.id]
    assert await talk.peek_news(ticket.id, "s1", began) == news
    assert [m.id for m in await talk.pending_messages(ticket.id)] == [message.id]


async def test_confirming_moves_the_mark_and_delivers_whole_messages_per_session(
    talk: TalkService, ticket: Ticket
) -> None:
    message = await talk.post_message(ticket.id, "use files", OWNER, "run")
    news = await talk.peek_news(ticket.id, "s1", START)
    assert news is not None
    await talk.confirm_news(ticket.id, "s1", news)
    assert await talk.peek_news(ticket.id, "s1", START) is None
    assert await talk.pending_messages(ticket.id) == []
    again = await talk.peek_news(ticket.id, "s2", START)
    assert again is not None
    assert again.message_ids == [message.id]


async def test_a_session_is_given_only_what_is_new_after_a_confirm(
    talk: TalkService, ticket: Ticket, clock: Clock
) -> None:
    await talk.add_comment(ticket.id, "one", OWNER)
    first = await talk.peek_news(ticket.id, "s1", START)
    assert first is not None
    await talk.confirm_news(ticket.id, "s1", first)
    clock.advance(seconds=5)
    await talk.add_comment(ticket.id, "two", OWNER)
    second = await talk.peek_news(ticket.id, "s1", START)
    assert second is not None
    assert second.text == f"{OWNER} commented on {ticket.id}: two"


async def test_no_news_is_none(talk: TalkService, ticket: Ticket) -> None:
    assert await talk.peek_news(ticket.id, "s1", START) is None


async def test_the_timeline_merges_every_kind_oldest_first_and_pages(
    talk: TalkService, ticket: Ticket, clock: Clock
) -> None:
    asked = await talk.ask(
        ticket.id, "Which colour?", [Choice(text="red"), Choice(text="blue")], by=RUN
    )
    clock.advance(seconds=1)
    await talk.answer(asked.question_id, Reply(choices=["red"]), by=OWNER, channel="reply")
    clock.advance(seconds=1)
    await talk.add_comment(ticket.id, "Nice", OWNER)
    await talk.post_message(ticket.id, "Go", OWNER, "run")  # same instant as the comment
    everything = await talk.activity_entries(ticket.id)
    assert [(e.kind, e.by, e.text) for e in everything.items] == [
        ("question", RUN, "Which colour?"),
        ("answer", OWNER, "red"),
        ("comment", OWNER, "Nice"),
        ("message", OWNER, "Go"),
    ]
    assert everything.items[1].data["channel"] == "reply"
    seen: list[str] = []
    cursor = None
    while True:
        page = await talk.activity_entries(ticket.id, limit=1, cursor=cursor)
        seen += [e.kind for e in page.items]
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == ["question", "answer", "comment", "message"]
    only = await talk.activity_entries(ticket.id, ["answer", "message"])
    assert [e.kind for e in only.items] == ["answer", "message"]


async def test_news_over_the_limit_leaves_the_rest_unread(
    talk: TalkService, ticket: Ticket, clock: Clock
) -> None:
    await talk.add_comment(ticket.id, "a" * 6000, OWNER)
    clock.advance(seconds=1)
    await talk.add_comment(ticket.id, "b" * 6000, OWNER)
    first = await talk.peek_news(ticket.id, "s1", START)
    assert first is not None
    assert first.text.endswith("a" * 6000)
    await talk.confirm_news(ticket.id, "s1", first)
    second = await talk.peek_news(ticket.id, "s1", START)
    assert second is not None
    assert second.text.endswith("b" * 6000)


async def test_the_timeline_pages_newest_first_across_equal_timestamps(
    talk: TalkService, ticket: Ticket, clock: Clock
) -> None:
    await talk.add_comment(ticket.id, "Older", OWNER)
    clock.advance(seconds=1)
    await talk.add_comment(ticket.id, "First comment", OWNER)
    await talk.post_message(ticket.id, "Message", OWNER, "run")
    await talk.add_comment(ticket.id, "Second comment", OWNER)

    cursor = None
    for expected in ("Message", "Second comment", "First comment", "Older"):
        page = await talk.activity_entries(ticket.id, limit=1, cursor=cursor, newest_first=True)
        assert [entry.text for entry in page.items] == [expected]
        cursor = page.next_cursor
    assert cursor is None


async def test_a_message_kept_for_the_next_run_is_no_news_for_this_one(
    talk: TalkService, ticket: Ticket
) -> None:
    await talk.post_message(ticket.id, "later", OWNER, "next_run")
    assert await talk.peek_news(ticket.id, "s1", START) is None
    assert [m.text for m in await talk.pending_messages(ticket.id)] == ["later"]


async def test_confirming_an_older_news_after_a_newer_one_does_not_move_the_mark_back(
    talk: TalkService, ticket: Ticket, clock: Clock
) -> None:
    await talk.add_comment(ticket.id, "one", OWNER)
    older = await talk.peek_news(ticket.id, "s1", START)
    clock.advance(seconds=5)
    await talk.add_comment(ticket.id, "two", OWNER)
    newer = await talk.peek_news(ticket.id, "s1", START)
    assert older is not None
    assert newer is not None
    await talk.confirm_news(ticket.id, "s1", newer)
    await talk.confirm_news(ticket.id, "s1", older)
    assert await talk.peek_news(ticket.id, "s1", START) is None
