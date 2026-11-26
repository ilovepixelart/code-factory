"""One timeline of a ticket from the tickets and the talk records, in pages.

Order worked by hand. Moment T0 is when the ticket is created, T1 is one minute later.
Records, in the order they were written:

    tickets: created (T0), stage (T1), note (T1)
    talk:    question (T0), comment (T0), message (T1)

Entries of one moment keep the order of the sources (tickets, then talk) and, within a source,
their own order (a ticket's records by id, the talk by question, answer, comment, message). That
holds in both directions: newest first reverses the moments, not the order inside one.
"""

from datetime import timedelta

import pytest

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.talk.service import TalkService
from code_factory.tickets.models import NewActivity, Ticket
from code_factory.tickets.service import ActivityService
from code_factory.timeline.rules import page_size
from code_factory.timeline.service import TimelineService
from talk_values import Clock
from ticket_values import NOW, OWNER

T1 = NOW + timedelta(minutes=1)
OLDEST_FIRST = ["created", "question", "comment", "stage", "note", "message"]
NEWEST_FIRST = ["stage", "note", "message", "created", "question", "comment"]


@pytest.fixture
async def written(
    ticket: Ticket, activity: ActivityService, talk: TalkService, talk_clock: Clock
) -> Ticket:
    """The six records of the module docstring; nothing is written in their order of moment."""
    await talk.ask(ticket.id, "Which colour?", [], by="run-1")
    await talk.add_comment(ticket.id, "Looks off", OWNER)
    stage = NewActivity(kind="stage", data={"from": "spec", "to": "build"}, at=T1)
    await activity.append(ticket.id, stage, by="board")
    await activity.append(ticket.id, NewActivity(kind="note", data={"text": "Hm"}, at=T1), by=OWNER)
    talk_clock.now = T1
    await talk.post_message(ticket.id, "Go on", OWNER, "run")
    return ticket


async def kinds_of(timeline: TimelineService, ticket: Ticket, **options: object) -> list[str]:
    page = await timeline.list_activity(ticket.id, **options)  # ty: ignore[invalid-argument-type]
    return [entry.kind for entry in page.items]


async def test_both_sources_merge_oldest_first_with_the_tickets_first_on_a_tie(
    timeline: TimelineService, written: Ticket
) -> None:
    page = await timeline.list_activity(written.id)
    assert [(e.kind, e.source, e.at) for e in page.items] == [
        ("created", "tickets", NOW),
        ("question", "talk", NOW),
        ("comment", "talk", NOW),
        ("stage", "tickets", T1),
        ("note", "tickets", T1),
        ("message", "talk", T1),
    ]
    assert page.next_cursor is None


async def test_talk_entries_carry_their_words_and_the_author(
    timeline: TimelineService, written: Ticket
) -> None:
    page = await timeline.list_activity(written.id, kinds=["question", "comment"])
    assert [(e.by, e.sentence) for e in page.items] == [
        ("run-1", "Which colour?"),
        (OWNER, "Looks off"),
    ]


async def test_newest_first_reverses_the_moments_and_keeps_the_order_within_one(
    timeline: TimelineService, written: Ticket
) -> None:
    assert await kinds_of(timeline, written, newest_first=True) == NEWEST_FIRST


async def test_oldest_first_pages_continue_across_a_tie_and_a_moment(
    timeline: TimelineService, written: Ticket
) -> None:
    first = await timeline.list_activity(written.id, limit=2)
    assert [e.kind for e in first.items] == ["created", "question"]
    assert first.next_cursor is not None
    second = await timeline.list_activity(written.id, limit=2, cursor=first.next_cursor)
    assert [e.kind for e in second.items] == ["comment", "stage"]
    assert second.next_cursor is not None
    third = await timeline.list_activity(written.id, limit=2, cursor=second.next_cursor)
    assert [e.kind for e in third.items] == ["note", "message"]
    assert third.next_cursor is None


async def test_newest_first_pages_continue_across_a_tie_and_a_moment(
    timeline: TimelineService, written: Ticket
) -> None:
    first = await timeline.list_activity(written.id, limit=4, newest_first=True)
    assert [e.kind for e in first.items] == NEWEST_FIRST[:4]
    assert first.next_cursor is not None
    rest = await timeline.list_activity(
        written.id, limit=4, cursor=first.next_cursor, newest_first=True
    )
    assert [e.kind for e in rest.items] == NEWEST_FIRST[4:]
    assert rest.next_cursor is None


async def test_a_page_that_ends_exactly_at_the_last_entry_has_no_cursor(
    timeline: TimelineService, written: Ticket
) -> None:
    exact = await timeline.list_activity(written.id, limit=6)
    assert len(exact.items) == 6
    assert exact.next_cursor is None
    short = await timeline.list_activity(written.id, limit=5)
    assert short.next_cursor is not None


async def test_a_record_written_after_a_page_does_not_move_the_next_page(
    timeline: TimelineService, written: Ticket, activity: ActivityService
) -> None:
    first = await timeline.list_activity(written.id, limit=4)
    await activity.append(
        written.id,
        NewActivity(kind="note", data={"text": "Late"}, at=T1 + timedelta(hours=1)),
        by=OWNER,
    )
    rest = await timeline.list_activity(written.id, limit=4, cursor=first.next_cursor)
    assert [e.kind for e in rest.items] == ["note", "message", "note"]


async def test_a_record_written_at_the_cursors_moment_does_not_repeat_or_hide_an_entry(
    timeline: TimelineService, ticket: Ticket, talk: TalkService, activity: ActivityService
) -> None:
    await talk.ask(ticket.id, "Q?", [], by="run-1")
    await talk.add_comment(ticket.id, "C", OWNER)
    first = await timeline.list_activity(ticket.id, limit=2)
    assert [e.kind for e in first.items] == ["created", "question"]
    await activity.append(ticket.id, NewActivity(kind="note", data={"text": "N"}, at=NOW), by=OWNER)
    rest = await timeline.list_activity(ticket.id, limit=2, cursor=first.next_cursor)
    assert [e.kind for e in rest.items] == ["comment"]


async def test_a_cursor_carried_to_a_wider_kinds_filter_continues_after_its_entry(
    timeline: TimelineService, written: Ticket
) -> None:
    first = await timeline.list_activity(written.id, kinds=["question", "stage"], limit=1)
    assert [e.kind for e in first.items] == ["question"]
    rest = await timeline.list_activity(written.id, cursor=first.next_cursor)
    assert [e.kind for e in rest.items] == ["comment", "stage", "note", "message"]


async def test_a_newest_first_cursor_carried_to_a_wider_filter_continues_after_its_entry(
    timeline: TimelineService, written: Ticket
) -> None:
    first = await timeline.list_activity(
        written.id, kinds=["message", "comment"], limit=1, newest_first=True
    )
    assert [e.kind for e in first.items] == ["message"]
    rest = await timeline.list_activity(written.id, cursor=first.next_cursor, newest_first=True)
    assert [e.kind for e in rest.items] == ["created", "question", "comment"]


async def test_kinds_keep_only_those_of_either_source(
    timeline: TimelineService, written: Ticket
) -> None:
    assert await kinds_of(timeline, written, kinds=["stage", "question"]) == ["question", "stage"]
    assert await kinds_of(timeline, written, kinds=["stage"]) == ["stage"]
    assert await kinds_of(timeline, written, kinds=["message", "comment"]) == [
        "comment",
        "message",
    ]
    assert await kinds_of(timeline, written, kinds=["nothing"]) == []


async def test_a_kinds_page_continues_among_the_kept_entries(
    timeline: TimelineService, written: Ticket
) -> None:
    first = await timeline.list_activity(
        written.id, kinds=["question", "stage", "message"], limit=2
    )
    assert [e.kind for e in first.items] == ["question", "stage"]
    rest = await timeline.list_activity(
        written.id, kinds=["question", "stage", "message"], limit=2, cursor=first.next_cursor
    )
    assert [e.kind for e in rest.items] == ["message"]
    assert rest.next_cursor is None


async def test_the_page_is_25_by_default(
    timeline: TimelineService, ticket: Ticket, activity: ActivityService
) -> None:
    for number in range(25):
        await activity.record_note(ticket.id, f"n{number}", "note", by=OWNER)
    default = await timeline.list_activity(ticket.id)
    assert len(default.items) == 25
    assert default.next_cursor is not None


@pytest.mark.parametrize(
    ("limit", "size"), [(None, 25), (1, 1), (100, 100), (101, 100), (500, 100), (0, 1), (-5, 1)]
)
def test_the_page_size_is_held_between_1_and_100(limit: int | None, size: int) -> None:
    assert page_size(limit) == size


async def test_an_unknown_ticket_does_not_exist(timeline: TimelineService) -> None:
    with pytest.raises(NotFoundError, match=r"CF-999999 does not exist"):
        await timeline.list_activity("CF-999999")


@pytest.mark.parametrize(
    "cursor",
    [
        "x",
        "2026-11-23T09:30:00+00:00|x",
        "2026-11-23T09:30:00|1",
        "|",
        "2026-11-23T09:30:00+00:00|2|0|1",
        "2026-11-23T09:30:00+00:00|1|4|1",
        "2026-11-23T09:30:00+00:00|0|1|1",
        "2026-11-23T09:30:00+00:00|0|0|-1",
    ],
)
async def test_a_cursor_this_feed_did_not_give_is_refused(
    timeline: TimelineService, ticket: Ticket, cursor: str
) -> None:
    with pytest.raises(BadRequestError, match="not one this list gave"):
        await timeline.list_activity(ticket.id, cursor=cursor)


async def test_a_talk_longer_than_a_talk_page_is_read_to_its_end(
    activity: ActivityService, talk: TalkService, ticket: Ticket
) -> None:
    timeline = TimelineService(activity, talk, talk_page=2)
    for number in range(5):
        await talk.add_comment(ticket.id, f"c{number}", OWNER)
    page = await timeline.list_activity(ticket.id)
    assert [e.sentence for e in page.items] == [
        "Created as a feature",
        *(f"c{n}" for n in range(5)),
    ]


async def test_a_limit_of_zero_is_held_to_one_entry(
    timeline: TimelineService, written: Ticket
) -> None:
    page = await timeline.list_activity(written.id, limit=0)
    assert [e.kind for e in page.items] == ["created"]
