"""Questions and answers through the talk service, against the test database.

Sentences and limits are the inbox spec's; expected values are worked by hand.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine, create_session_factory
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.talk.models import Choice, QuestionAsked, QuestionFilter, Reply
from code_factory.talk.service import TalkService
from code_factory.tickets.models import NewTicket, Ticket
from code_factory.tickets.service import TicketService
from talk_values import OWNER, RUN

COLOUR = "Which colour?"


def choices(*names: str) -> list[Choice]:
    return [Choice(text=name) for name in names]


async def ask(
    talk: TalkService, ticket: str, words: str = COLOUR, *names: str, document: str | None = None
) -> QuestionAsked:
    return await talk.ask(ticket, words, choices(*names), by=RUN, document=document)


async def test_an_asked_question_keeps_its_author_run_and_choices(
    talk: TalkService, ticket: Ticket
) -> None:
    asked = await talk.ask(
        ticket.id,
        "  Which colour?  ",
        [Choice(text="red"), Choice(text="blue", recommended=True, reason="matches the logo")],
        document="spec.md",
        by=RUN,
        run_id="r-9",
    )
    assert (asked.created, asked.status) == (True, "open")
    got = await talk.get(asked.question_id)
    assert got.model_dump(exclude={"id", "created_at"}) == {
        "ticket_id": ticket.id,
        "document": "spec",
        "index": 0,
        "text": "Which colour?",
        "topic": "",
        "several": False,
        "choices": [
            {
                "text": "blue",
                "recommended": True,
                "reason": "matches the logo",
                "description": "",
                "preview": "",
                "ticked": False,
            },
            {
                "text": "red",
                "recommended": False,
                "reason": "",
                "description": "",
                "preview": "",
                "ticked": False,
            },
        ],
        "asked_by": RUN,
        "run_id": "r-9",
        "status": "open",
        "answer": None,
    }


async def test_the_same_open_question_is_one_question(talk: TalkService, ticket: Ticket) -> None:
    first = await ask(talk, ticket.id)
    again = await ask(talk, ticket.id, "  Which colour? ")
    assert (again.question_id, again.created) == (first.question_id, False)
    other_document = await ask(talk, ticket.id, COLOUR, document="uat")
    assert other_document.created is True
    assert other_document.question_id != first.question_id


async def test_the_same_text_after_an_answer_is_a_new_question(
    talk: TalkService, ticket: Ticket
) -> None:
    first = await ask(talk, ticket.id)
    await talk.answer(first.question_id, Reply(text="blue"), by=OWNER, channel="http")
    second = await ask(talk, ticket.id)
    assert second.created is True
    assert second.question_id != first.question_id


async def test_the_twentieth_open_question_is_taken_and_the_twenty_first_refused(
    talk: TalkService, ticket: Ticket
) -> None:
    for number in range(20):
        await ask(talk, ticket.id, f"Question {number}?")
    with pytest.raises(
        ConflictError,
        match=rf"^limit: {ticket.id} already has 20 open questions\. Answer or withdraw one\.$",
    ):
        await ask(talk, ticket.id, "Question 20?")
    assert (await talk.open_counts([ticket.id]))[ticket.id] == 20


async def test_asking_on_a_ticket_that_is_not_there_is_not_found(talk: TalkService) -> None:
    with pytest.raises(NotFoundError, match=r"^CF-99999 does not exist"):
        await ask(talk, "CF-99999")
    with pytest.raises(BadRequestError, match=r"is not a ticket id CF-<n>"):
        await ask(talk, "nonsense")


async def test_a_bad_question_is_refused_before_any_row(talk: TalkService, ticket: Ticket) -> None:
    with pytest.raises(BadRequestError, match=r"^a question needs words$"):
        await ask(talk, ticket.id, " ")
    assert (await talk.list(QuestionFilter(ticket_id=ticket.id, status="all"))).items == []


async def test_an_unknown_question_is_not_found(talk: TalkService) -> None:
    with pytest.raises(NotFoundError, match=r"^no question 424242$"):
        await talk.get(424242)


async def test_listing_filters_by_ticket_status_and_document(
    talk: TalkService, ticket: Ticket, tickets: TicketService
) -> None:
    other = await tickets.create(NewTicket(repository="sample", title="Other"), by=OWNER)
    one = await ask(talk, ticket.id, "One?")
    two = await ask(talk, ticket.id, "Two?", document="uat")
    await ask(talk, other.id, "Three?")
    await talk.answer(one.question_id, Reply(text="yes"), by=OWNER, channel="http")

    def ids(page) -> list[int]:  # noqa: ANN001
        return [q.id for q in page.items]

    mine = QuestionFilter(ticket_id=ticket.id)
    assert ids(await talk.list(mine)) == [two.question_id]
    assert ids(await talk.list(mine.model_copy(update={"status": "answered"}))) == [one.question_id]
    assert ids(await talk.list(mine.model_copy(update={"status": "all"}))) == [
        one.question_id,
        two.question_id,
    ]
    assert ids(
        await talk.list(mine.model_copy(update={"status": "all", "document": "uat.md"}))
    ) == [two.question_id]


async def test_pages_follow_one_another_without_gaps_or_repeats(
    talk: TalkService, ticket: Ticket
) -> None:
    made = [(await ask(talk, ticket.id, f"Q{n}?")).question_id for n in range(5)]
    seen: list[int] = []
    cursor = None
    pages = 0
    while True:
        page = await talk.list(QuestionFilter(ticket_id=ticket.id), limit=2, cursor=cursor)
        seen += [q.id for q in page.items]
        pages += 1
        cursor = page.next_cursor
        if cursor is None:
            break
    assert (seen, pages) == (made, 3)


async def test_an_answer_stores_the_words_and_picks_and_closes_the_question(
    talk: TalkService, ticket: Ticket
) -> None:
    asked = await ask(talk, ticket.id, COLOUR, "red", "blue")
    done = await talk.answer(asked.question_id, Reply(choices=["blue"]), by=OWNER, channel="mcp")
    assert done.model_dump() == {
        "question_id": asked.question_id,
        "ticket_id": ticket.id,
        "text": COLOUR,
        "answer": "blue",
        "status": "answered",
    }
    got = await talk.get(asked.question_id)
    assert got.status == "answered"
    assert got.answer is not None
    assert (got.answer.text, got.answer.picked, got.answer.by, got.answer.channel) == (
        "blue",
        ["blue"],
        OWNER,
        "mcp",
    )


async def test_a_second_answer_without_replace_is_refused_and_writes_nothing(
    talk: TalkService, ticket: Ticket
) -> None:
    asked = await ask(talk, ticket.id)
    await talk.answer(asked.question_id, Reply(text="blue"), by=OWNER, channel="http")
    with pytest.raises(ConflictError, match=r"^Which colour\? is already answered: blue$"):
        await talk.answer(asked.question_id, Reply(text="green"), by=OWNER, channel="http")
    kept = (await talk.get(asked.question_id)).answer
    assert kept is not None
    assert kept.text == "blue"


async def test_replacing_an_answer_keeps_the_history_and_shows_the_newest(
    talk: TalkService, ticket: Ticket, db_session: AsyncSession
) -> None:
    asked = await ask(talk, ticket.id)
    await talk.answer(asked.question_id, Reply(text="blue"), by=OWNER, channel="http")
    await talk.answer(
        asked.question_id, Reply(text="green"), replace=True, by=OWNER, channel="reply"
    )
    shown = (await talk.list_for_ticket(ticket.id))[0]
    assert shown.answer is not None
    assert (shown.answer.text, shown.answer.channel) == ("green", "reply")
    rows = await db_session.scalar(
        text("select count(*) from talk_question_answers where question_id = :q"),
        {"q": asked.question_id},
    )
    assert rows == 2


async def test_a_bad_reply_leaves_the_question_open(talk: TalkService, ticket: Ticket) -> None:
    asked = await ask(talk, ticket.id, COLOUR, "red", "blue")
    with pytest.raises(BadRequestError, match=r"^pink is not one of its choices: red, blue$"):
        await talk.answer(asked.question_id, Reply(choices=["pink"]), by=OWNER, channel="http")
    assert (await talk.get(asked.question_id)).status == "open"


async def test_a_withdrawn_question_cannot_be_answered_and_withdrawing_twice_is_fine(
    talk: TalkService, ticket: Ticket
) -> None:
    asked = await ask(talk, ticket.id)
    await talk.withdraw(asked.question_id, by=OWNER)
    await talk.withdraw(asked.question_id, by=OWNER)
    assert (await talk.get(asked.question_id)).status == "withdrawn"
    with pytest.raises(ConflictError, match=r"^Which colour\? was withdrawn$"):
        await talk.answer(asked.question_id, Reply(text="blue"), by=OWNER, channel="http")
    assert (await talk.open_counts([ticket.id]))[ticket.id] == 0


async def test_an_answered_question_cannot_be_withdrawn(talk: TalkService, ticket: Ticket) -> None:
    asked = await ask(talk, ticket.id)
    await talk.answer(asked.question_id, Reply(text="blue"), by=OWNER, channel="http")
    with pytest.raises(ConflictError, match=r"^Which colour\? is answered already$"):
        await talk.withdraw(asked.question_id, by=OWNER)


async def test_answering_by_position_and_shown_text_finds_the_question(
    talk: TalkService, ticket: Ticket
) -> None:
    await ask(talk, ticket.id, "First?", document="spec")
    second = await ask(talk, ticket.id, "Second?", document="spec")
    await ask(talk, ticket.id, "Other?", document="uat")
    done = await talk.answer_shown(
        ticket.id, "spec.md", 1, " Second? ", Reply(text="yes"), by=OWNER, channel="http"
    )
    assert (done.question_id, done.text, done.answer) == (second.question_id, "Second?", "yes")
    with pytest.raises(ConflictError, match=r"^the question changed: it now asks Second\?$"):
        await talk.answer_shown(
            ticket.id, "spec", 1, "First?", Reply(text="x"), replace=True, by=OWNER, channel="http"
        )
    with pytest.raises(NotFoundError, match=r"^no question 2 in spec.md$"):
        await talk.answer_shown(
            ticket.id, "spec.md", 2, "Second?", Reply(text="x"), by=OWNER, channel="http"
        )


async def test_positions_count_per_document_and_stay_when_later_questions_arrive(
    talk: TalkService, ticket: Ticket
) -> None:
    await ask(talk, ticket.id, "A?", document="spec")
    await ask(talk, ticket.id, "B?", document="uat")
    await ask(talk, ticket.id, "C?", document="spec")
    before = {q.text: q.index for q in await talk.list_for_ticket(ticket.id)}
    await ask(talk, ticket.id, "D?", document="spec")
    after = {q.text: q.index for q in await talk.list_for_ticket(ticket.id)}
    assert before == {"A?": 0, "B?": 0, "C?": 1}
    assert after == {"A?": 0, "B?": 0, "C?": 1, "D?": 2}


async def test_open_counts_cover_every_ticket_asked_for_in_one_query(
    talk: TalkService, ticket: Ticket, connection: AsyncConnection
) -> None:
    await ask(talk, ticket.id, "A?")
    await ask(talk, ticket.id, "B?")
    statements: list[str] = []

    def record(_c: object, _cur: object, statement: str, *_rest: object) -> None:
        statements.append(statement)

    event.listen(connection.sync_connection, "before_cursor_execute", record)
    try:
        counts = await talk.open_counts([ticket.id, "CF-900001", "CF-900002"])
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", record)
    assert counts == {ticket.id: 2, "CF-900001": 0, "CF-900002": 0}
    assert len([s for s in statements if "talk_questions" in s]) == 1


@asynccontextmanager
async def committed_ticket(settings: Settings) -> AsyncGenerator[tuple[TalkService, str]]:
    """A talk service on real sessions and a committed ticket row, deleted (with its talk) after."""
    engine = create_engine(settings)
    uow = UnitOfWork(create_session_factory(engine))
    try:
        async with uow() as session:
            number = await session.scalar(
                text(
                    "insert into tickets (repository, title) "
                    "values ('sample', 'Race') returning number"
                )
            )
        try:
            yield TalkService(uow), f"CF-{number}"
        finally:
            async with uow() as session:
                await session.execute(text("delete from tickets where number = :n"), {"n": number})
    finally:
        await engine.dispose()


async def test_two_answers_at_once_leave_exactly_one_winner(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> None:
    async with committed_ticket(settings) as (service, ticket):
        asked = await ask(service, ticket)
        results = await asyncio.gather(
            *(
                service.answer(asked.question_id, Reply(text=word), by=OWNER, channel="http")
                for word in ("blue", "green")
            ),
            return_exceptions=True,
        )
        wins = [r for r in results if not isinstance(r, BaseException)]
        refused = [r for r in results if isinstance(r, ConflictError)]
        assert (len(wins), len(refused)) == (1, 1)


async def test_a_cursor_that_is_not_an_id_is_refused(talk: TalkService, ticket: Ticket) -> None:
    for bad in ("abc", "\u00b2", "99999999999999999999"):
        with pytest.raises(BadRequestError, match=r"^that cursor is not one this list gave"):
            await talk.list(QuestionFilter(ticket_id=ticket.id), cursor=bad)
    with pytest.raises(BadRequestError, match=r"^that cursor is not one this list gave"):
        await talk.activity_entries(ticket.id, cursor="abc")


async def test_the_same_question_asked_twice_at_once_is_one_question(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> None:
    async with committed_ticket(settings) as (service, ticket):
        results = await asyncio.gather(*(ask(service, ticket) for _ in range(2)))
        assert sorted(r.created for r in results) == [False, True]
        assert len({r.question_id for r in results}) == 1


async def test_a_deleted_ticket_takes_its_talk_with_it(
    talk: TalkService, bare_ticket: str, db_session: AsyncSession
) -> None:
    asked = await ask(talk, bare_ticket)
    await talk.answer(asked.question_id, Reply(text="blue"), by=OWNER, channel="http")
    await talk.add_comment(bare_ticket, "Looks good", OWNER)
    await db_session.execute(
        text("delete from tickets where number = :n"), {"n": int(bare_ticket.removeprefix("CF-"))}
    )
    left = await db_session.execute(
        text(
            "select (select count(*) from talk_questions where ticket_number = :n),"
            " (select count(*) from talk_question_answers where question_id = :q),"
            " (select count(*) from talk_posts where ticket_number = :n)"
        ),
        {"n": int(bare_ticket.removeprefix("CF-")), "q": asked.question_id},
    )
    assert tuple(left.one()) == (0, 0, 0)
