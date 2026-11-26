"""The talk module's public API: questions, answers, comments, messages and news.

Each method is one unit of work in its own session. `by` is the actor's subject. A ticket is
addressed by its id `CF-<n>`; the tables hold its number and the ticket's own module is never
imported (it reads talk, not the other way round).
"""

import builtins
from collections.abc import Callable
from datetime import datetime
from typing import Any, get_args

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import ConflictError
from code_factory.talk.models import (
    Answered,
    Channel,
    Choice,
    EntryKind,
    Message,
    News,
    NewsEntry,
    PostId,
    Question,
    QuestionAsked,
    QuestionFilter,
    QuestionPage,
    QuestionWait,
    Reply,
    Route,
    TalkEntry,
    TalkEntryPage,
)
from code_factory.talk.repository import TalkRepository
from code_factory.talk.rules import (
    answer_target,
    check_question,
    check_reply,
    check_topic,
    comment_text,
    document_name,
    fitting,
    message_text,
    news_lines,
    ticket_number,
)
from code_factory.talk.service.common import (
    OPEN_LIMIT,
    PAGE_DEFAULT,
    PAGE_MAX,
    check_id,
    no_question,
    no_ticket,
    page_after,
    question_conditions,
    to_message,
    to_question,
    utc_now,
)
from code_factory.talk.service.timeline import entries_of, entry_cursor, entry_cursor_text
from code_factory.talk.tables import PostRow, QuestionRow


class TalkService:
    """Questions agents ask the owner, and what the owner says back."""

    def __init__(self, uow: UnitOfWork, clock: Callable[[], datetime] = utc_now) -> None:
        self._uow = uow
        self._clock = clock

    async def question_wait(self, since: datetime, until: datetime) -> QuestionWait:
        """Wait from asking to the owner's first recorded answer."""
        async with self._uow() as session:
            return await TalkRepository(session).question_wait(since, until)

    async def ask(  # noqa: PLR0913  # the spec's signature
        self,
        ticket: str,
        text: str,
        choices: builtins.list[Choice],
        *,
        document: str | None = None,
        several: bool = False,
        topic: str = "",
        by: str,
        run_id: str | None = None,
    ) -> QuestionAsked:
        """Ask the owner; an equal open question on the ticket is returned, not asked again."""
        number = ticket_number(ticket)
        words, checked = check_question(text, choices, several=several)
        label = check_topic(topic)
        where = document_name(document)
        async with self._uow() as session:
            repository = TalkRepository(session)
            await repository.lock_ticket(number)
            same = await repository.find_open(number, words, where)
            if same is not None:
                return QuestionAsked(question_id=same.id, created=False, status="open")
            if await repository.count_open(number) >= OPEN_LIMIT:
                msg = (
                    f"limit: {ticket} already has {OPEN_LIMIT} open questions. "
                    "Answer or withdraw one."
                )
                raise ConflictError(msg)
            row = await repository.insert_question(
                {
                    "ticket_number": number,
                    "document": where,
                    "text": words,
                    "several": several,
                    "topic": label,
                    "choices": [
                        {
                            "text": c.text,
                            "recommended": c.recommended,
                            "reason": c.reason,
                            "description": c.description,
                            "preview": c.preview,
                        }
                        for c in checked
                    ],
                    "asked_by": by,
                    "run_id": run_id or "",
                    "created_at": self._clock(),
                }
            )
            if row is None:
                raise no_ticket(number)
            return QuestionAsked(question_id=row.id, created=True, status="open")

    async def get(self, question_id: int) -> Question:
        """One question; `NotFoundError` when there is none."""
        async with self._uow() as session:
            repository = TalkRepository(session)
            found = await repository.question(check_id(question_id))
            if found is None:
                raise no_question(question_id)
            answers = await repository.latest_answers([question_id])
            return to_question(found[0], found[1], answers.get(question_id))

    async def list(
        self,
        where: QuestionFilter | None = None,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> QuestionPage:
        """Questions by id (open ones by default); `limit` is 25 by default, 100 at most."""
        size = min(max(limit or PAGE_DEFAULT, 1), PAGE_MAX)
        async with self._uow() as session:
            repository = TalkRepository(session)
            found = await repository.questions(
                question_conditions(where or QuestionFilter()),
                limit=size + 1,
                after=page_after(cursor),
            )
            shown = found[:size]
            answers = await repository.latest_answers([row.id for row, _ in shown])
        items = [to_question(row, index, answers.get(row.id)) for row, index in shown]
        more = len(found) > size
        return QuestionPage(items=items, next_cursor=str(items[-1].id) if more else None)

    async def list_for_ticket(self, ticket: str) -> builtins.list[Question]:
        """Every question of the ticket, withdrawn ones included, with positions and answers."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            repository = TalkRepository(session)
            found = await repository.questions([QuestionRow.ticket_number == number])
            answers = await repository.latest_answers([row.id for row, _ in found])
        return [to_question(row, index, answers.get(row.id)) for row, index in found]

    async def open_counts(self, tickets: builtins.list[str]) -> dict[str, int]:
        """Open questions per ticket, every ticket asked for present, in one query."""
        numbers = [ticket_number(t) for t in tickets]
        async with self._uow() as session:
            counts = await TalkRepository(session).open_counts(numbers)
        return {t: counts.get(n, 0) for t, n in zip(tickets, numbers, strict=True)}

    async def answer(
        self,
        question_id: int,
        reply: Reply,
        *,
        replace: bool = False,
        by: str,
        channel: Channel,
    ) -> Answered:
        """Record an answer. A question answered already needs `replace`; both stay as history."""
        async with self._uow() as session:
            repository = TalkRepository(session)
            found = await repository.question(check_id(question_id), for_update=True)
            if found is None:
                raise no_question(question_id)
            row, index = found
            await repository.lock_ticket(row.ticket_number)
            latest = (await repository.latest_answers([question_id])).get(question_id)
            question = to_question(row, index, latest)
            if question.status == "withdrawn":
                raise ConflictError(f"{row.text} was withdrawn")
            if latest is not None and not replace:
                raise ConflictError(f"{row.text} is already answered: {latest.text}")
            words, picked = check_reply(question, reply.choices, reply.text)
            now = self._clock()
            await repository.add_answer(
                {
                    "question_id": question_id,
                    "text": words,
                    "picked": picked,
                    "by": by,
                    "channel": channel,
                    "created_at": now,
                }
            )
            row.answered_at = row.answered_at or now
            return Answered(
                question_id=question_id,
                ticket_id=question.ticket_id,
                text=row.text,
                answer=words,
                status="answered",
            )

    async def answer_shown(  # noqa: PLR0913  # the spec's signature
        self,
        ticket: str,
        document: str,
        index: int,
        shown: str,
        reply: Reply,
        *,
        replace: bool = False,
        by: str,
        channel: Channel,
    ) -> Answered:
        """Answer the question at (`document`, `index`) of the ticket if it still reads `shown`."""
        target = answer_target(await self.list_for_ticket(ticket), document, index, shown)
        return await self.answer(target.id, reply, replace=replace, by=by, channel=channel)

    async def withdraw(self, question_id: int, *, by: str) -> None:
        """Take a question back; withdrawing one already withdrawn changes nothing."""
        async with self._uow() as session:
            repository = TalkRepository(session)
            found = await repository.question(check_id(question_id), for_update=True)
            if found is None:
                raise no_question(question_id)
            row = found[0]
            if row.withdrawn_at is not None:
                return
            if row.answered_at is not None:
                raise ConflictError(f"{row.text} is answered already")
            row.withdrawn_at, row.withdrawn_by = self._clock(), by

    async def _post(self, ticket: str, values: dict[str, Any]) -> PostRow:
        number = ticket_number(ticket)
        async with self._uow() as session:
            repository = TalkRepository(session)
            await repository.lock_ticket(number)
            row = await repository.insert_post(
                {"ticket_number": number, "created_at": self._clock(), **values}
            )
        if row is None:
            raise no_ticket(number)
        return row

    async def add_comment(
        self, ticket: str, text: str, by: str, *, path: str | None = None, line: int | None = None
    ) -> PostId:
        """Record the owner's comment, about a place in the code when `path` is given."""
        words = comment_text(text, path, line)
        place = (path or "").strip()
        row = await self._post(
            ticket,
            {
                "kind": "comment",
                "author": by,
                "text": words,
                "path": place,
                "line": line if place else None,
            },
        )
        return PostId(id=row.id)

    async def post_message(self, ticket: str, text: str, by: str, route: Route) -> Message:
        """Record the owner's message for the running agent (`run`) or the next run."""
        row = await self._post(
            ticket, {"kind": "message", "author": by, "text": message_text(text), "route": route}
        )
        return to_message(row)

    async def pending_messages(self, ticket: str) -> builtins.list[Message]:
        """Messages no run received yet, oldest first."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            rows = await TalkRepository(session).pending_messages(number)
        return [to_message(row) for row in rows]

    async def mark_delivered(
        self, ticket: str, message_ids: builtins.list[int], run_id: str
    ) -> None:
        """Mark messages of the ticket as received by `run_id`; already delivered ones stay so."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            await TalkRepository(session).mark_delivered(number, message_ids, run_id, self._clock())

    async def peek_news(self, ticket: str, session_id: str, since: datetime) -> News | None:
        """What was said on the ticket since `since` that the session has not been given.

        Nothing changes until `confirm_news`, so a hook that fails before injecting leaves the
        news waiting.
        """
        number = ticket_number(ticket)
        async with self._uow() as session:
            repository = TalkRepository(session)
            mark = await repository.mark(number, session_id)
            post_mark, answer_mark = (mark.post_id, mark.answer_id) if mark else (0, 0)
            posts = await repository.posts_after(number, since=since, after=post_mark)
            answers = await repository.answers_after(number, since=since, after=answer_mark)
        dated: builtins.list[tuple[datetime, int, int, NewsEntry]] = [
            (
                p.created_at,
                1,
                p.id,
                NewsEntry(
                    kind="message" if p.kind == "message" else "comment",
                    text=p.text,
                    author=p.author,
                    message_id=p.id if p.kind == "message" else None,
                ),
            )
            for p in posts
        ] + [
            (a.created_at, 0, a.id, NewsEntry(kind="answer", text=a.text, question=words))
            for a, words in answers
        ]
        if not dated:
            return None
        dated.sort(key=lambda item: item[:3])
        entries = [item[3] for item in dated]
        text, whole = news_lines(entries, ticket)
        given = dated[: fitting(entries, ticket)]
        return News(
            text=text,
            through_post=max((i for _, rank, i, _ in given if rank == 1), default=post_mark),
            through_answer=max((i for _, rank, i, _ in given if rank == 0), default=answer_mark),
            message_ids=whole,
        )

    async def confirm_news(self, ticket: str, session_id: str, news: News) -> None:
        """Move the session's mark past `news` and mark the whole messages in it delivered."""
        number = ticket_number(ticket)
        now = self._clock()
        async with self._uow() as session:
            repository = TalkRepository(session)
            await repository.move_mark(
                number, session_id, news.through_post, news.through_answer, now
            )
            if news.message_ids:
                await repository.mark_delivered(number, news.message_ids, session_id, now)

    async def activity_entries(
        self,
        ticket: str,
        kinds: builtins.list[EntryKind] | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> TalkEntryPage:
        """The ticket's talk oldest first, for its timeline; `kinds` narrows it."""
        number = ticket_number(ticket)
        size = min(max(limit or PAGE_DEFAULT, 1), PAGE_MAX)
        after = entry_cursor(cursor)
        wanted: builtins.list[EntryKind] = [
            k for k in get_args(EntryKind) if kinds is None or k in kinds
        ]
        entries: builtins.list[tuple[tuple[datetime, int, int], TalkEntry]] = []
        async with self._uow() as session:
            repository = TalkRepository(session)
            for kind in wanted:
                rows = await repository.entries(number, kind, limit=size + 1, cursor=after)
                entries += entries_of(ticket, kind, rows)
        entries.sort(key=lambda item: item[0])
        page = [entry for _, entry in entries[:size]]
        last = entries[size - 1][0] if len(entries) > size else None
        return TalkEntryPage(items=page, next_cursor=entry_cursor_text(last))
