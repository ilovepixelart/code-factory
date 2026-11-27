"""Queries over the talk tables. Every method runs in the session it is given."""

from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import ScalarSelect, extract, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.db import lock_until_commit
from code_factory.platform.errors import ConflictError
from code_factory.talk.models import QuestionWait
from code_factory.talk.tables import AnswerRow, NewsMarkRow, PostRow, QuestionRow

FOREIGN_KEY_VIOLATION = "23503"
LOCK_NOT_AVAILABLE = "55P03"
# How long a write waits for another one on the same ticket, so a stuck transaction cannot hold
# every later writer of that ticket without bound.
LOCK_TIMEOUT_MS = 10_000
# The advisory lock's key is the hash of this name seeded with the ticket number, so it cannot
# meet another module's advisory lock on the same number.
LOCK_KEY = "code_factory.talk.ticket"
OPEN = (QuestionRow.answered_at.is_(None), QuestionRow.withdrawn_at.is_(None))


def _position() -> ScalarSelect[int]:
    """The zero based position of a question among its ticket's of the same document."""
    other = QuestionRow.__table__.alias("earlier")
    return (
        select(func.count())
        .where(
            other.c.ticket_number == QuestionRow.ticket_number,
            other.c.document == QuestionRow.document,
            other.c.id < QuestionRow.id,
        )
        .scalar_subquery()
    )


class TalkRepository:
    """Questions, answers, posts and news marks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def question_wait(self, since: datetime, until: datetime) -> QuestionWait:
        """Count first answers and report the median time since the question was asked."""
        duration = extract("epoch", QuestionRow.answered_at - QuestionRow.created_at)
        result = await self._session.execute(
            select(func.count(), func.percentile_cont(0.5).within_group(duration)).where(
                QuestionRow.answered_at >= since,
                QuestionRow.answered_at < until,
                QuestionRow.answered_at >= QuestionRow.created_at,
            )
        )
        total, median = result.one()
        return QuestionWait(answered=total, median_seconds=median)

    @asynccontextmanager
    async def _lock_wait(self) -> AsyncGenerator[None]:
        """Run the statements inside for at most `LOCK_TIMEOUT_MS` of waiting for a lock."""
        await self._session.execute(
            text("select set_config('lock_timeout', :ms, true)"), {"ms": f"{LOCK_TIMEOUT_MS}ms"}
        )
        try:
            yield
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) != LOCK_NOT_AVAILABLE:
                raise
            msg = "another change to the same ticket is in progress: try again in a moment"
            raise ConflictError(msg) from error

    async def lock_ticket(self, number: int) -> None:
        """Serialise the writers of one ticket's talk until the transaction ends."""
        async with self._lock_wait():
            await lock_until_commit(self._session, f"{LOCK_KEY}:{number}")

    async def _insert(self, row: QuestionRow | PostRow) -> bool:
        """Add `row`; false when its ticket does not exist."""
        try:
            async with self._session.begin_nested():
                self._session.add(row)
                await self._session.flush()
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == FOREIGN_KEY_VIOLATION:
                return False
            raise
        return True

    async def insert_question(self, values: dict[str, Any]) -> QuestionRow | None:
        """Insert a question; `None` when the ticket does not exist."""
        row = QuestionRow(**values)
        return row if await self._insert(row) else None

    async def find_open(self, number: int, words: str, document: str) -> QuestionRow | None:
        """The open question of the ticket that asks `words` of `document`."""
        return await self._session.scalar(
            select(QuestionRow).where(
                QuestionRow.ticket_number == number,
                QuestionRow.text == words,
                QuestionRow.document == document,
                *OPEN,
            )
        )

    async def count_open(self, number: int) -> int:
        """How many questions of the ticket wait for an answer."""
        return (
            await self._session.scalar(
                select(func.count()).where(QuestionRow.ticket_number == number, *OPEN)
            )
            or 0
        )

    async def question(
        self, question_id: int, *, for_update: bool = False
    ) -> tuple[QuestionRow, int] | None:
        """A question with its position, locked against concurrent writers when asked."""
        query = select(QuestionRow, _position()).where(QuestionRow.id == question_id)
        if for_update:
            async with self._lock_wait():
                found = (await self._session.execute(query.with_for_update(of=QuestionRow))).first()
        else:
            found = (await self._session.execute(query)).first()
        return None if found is None else (found[0], found[1])

    async def questions(
        self,
        conditions: Sequence[Any],
        *,
        limit: int | None = None,
        after: int | None = None,
    ) -> list[tuple[QuestionRow, int]]:
        """Questions matching `conditions` by id, each with its position."""
        query = select(QuestionRow, _position()).where(*conditions).order_by(QuestionRow.id)
        if after is not None:
            query = query.where(QuestionRow.id > after)
        if limit is not None:
            query = query.limit(limit)
        return [(row, index) for row, index in (await self._session.execute(query)).all()]

    async def latest_answers(self, question_ids: Sequence[int]) -> dict[int, AnswerRow]:
        """The newest answer of each of the questions that has one."""
        if not question_ids:
            return {}
        rows = await self._session.scalars(
            select(AnswerRow).where(AnswerRow.question_id.in_(question_ids)).order_by(AnswerRow.id)
        )
        return {row.question_id: row for row in rows}

    async def add_answer(self, values: dict[str, Any]) -> AnswerRow:
        """Append an answer."""
        row = AnswerRow(**values)
        self._session.add(row)
        await self._session.flush()
        return row

    async def open_counts(self, numbers: Sequence[int]) -> dict[int, int]:
        """The open questions of each ticket that has any, in one query."""
        rows = await self._session.execute(
            select(QuestionRow.ticket_number, func.count())
            .where(QuestionRow.ticket_number.in_(numbers), *OPEN)
            .group_by(QuestionRow.ticket_number)
        )
        return dict(rows.all())

    async def insert_post(self, values: dict[str, Any]) -> PostRow | None:
        """Insert a comment or message; `None` when the ticket does not exist."""
        row = PostRow(**values)
        return row if await self._insert(row) else None

    async def pending_messages(self, number: int) -> list[PostRow]:
        """The messages of the ticket no run received, oldest first."""
        rows = await self._session.scalars(
            select(PostRow)
            .where(
                PostRow.ticket_number == number,
                PostRow.kind == "message",
                PostRow.delivered_at.is_(None),
            )
            .order_by(PostRow.id)
        )
        return list(rows)

    async def mark_delivered(
        self, number: int, ids: Sequence[int], run_id: str, at: datetime
    ) -> None:
        """Mark the undelivered messages `ids` of the ticket as received by `run_id`."""
        await self._session.execute(
            update(PostRow)
            .where(
                PostRow.ticket_number == number,
                PostRow.kind == "message",
                PostRow.id.in_(ids),
                PostRow.delivered_at.is_(None),
            )
            .values(delivered_at=at, delivered_to=run_id)
        )

    async def posts_after(self, number: int, *, since: datetime, after: int) -> list[PostRow]:
        """Posts of the ticket made at or after `since` with an id above `after`."""
        rows = await self._session.scalars(
            select(PostRow)
            .where(
                PostRow.ticket_number == number,
                PostRow.created_at >= since,
                PostRow.id > after,
                PostRow.route != "next_run",
            )
            .order_by(PostRow.created_at, PostRow.id)
        )
        return list(rows)

    async def answers_after(
        self, number: int, *, since: datetime, after: int
    ) -> list[tuple[AnswerRow, str]]:
        """Answers on the ticket since `since` above `after`, each with its question's text."""
        rows = await self._session.execute(
            select(AnswerRow, QuestionRow.text)
            .join(QuestionRow, QuestionRow.id == AnswerRow.question_id)
            .where(
                QuestionRow.ticket_number == number,
                AnswerRow.created_at >= since,
                AnswerRow.id > after,
            )
            .order_by(AnswerRow.created_at, AnswerRow.id)
        )
        return [(answer, words) for answer, words in rows.all()]

    async def mark(self, number: int, session_id: str) -> NewsMarkRow | None:
        """How far the session was given the ticket's talk."""
        return await self._session.get(NewsMarkRow, (number, session_id))

    async def move_mark(
        self, number: int, session_id: str, post_id: int, answer_id: int, at: datetime
    ) -> None:
        """Move the session's mark forward, never back."""
        statement = insert(NewsMarkRow).values(
            ticket_number=number,
            session_id=session_id,
            post_id=post_id,
            answer_id=answer_id,
            updated_at=at,
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["ticket_number", "session_id"],
                set_={
                    "post_id": func.greatest(NewsMarkRow.post_id, post_id),
                    "answer_id": func.greatest(NewsMarkRow.answer_id, answer_id),
                    "updated_at": at,
                },
            )
        )

    async def entries(
        self,
        number: int,
        kind: str,
        *,
        limit: int,
        cursor: tuple[datetime, int, int] | None,
        newest_first: bool,
    ) -> list[Any]:
        """Rows of one kind of the ticket's talk after the cursor `(at, kind rank, id)`."""
        rank = ENTRY_RANK[kind]
        if kind == "question":
            query = select(QuestionRow).where(QuestionRow.ticket_number == number)
            at, key = QuestionRow.created_at, QuestionRow.id
        elif kind == "answer":
            query = (
                select(AnswerRow, QuestionRow.text)
                .join(QuestionRow, QuestionRow.id == AnswerRow.question_id)
                .where(QuestionRow.ticket_number == number)
            )
            at, key = AnswerRow.created_at, AnswerRow.id
        else:
            query = select(PostRow).where(PostRow.ticket_number == number, PostRow.kind == kind)
            at, key = PostRow.created_at, PostRow.id
        if cursor is not None:
            when, cursor_rank, last = cursor
            later = at < when if newest_first else at > when
            rank_follows = rank < cursor_rank if newest_first else rank > cursor_rank
            if rank == cursor_rank:
                key_follows = key < last if newest_first else key > last
                later |= (at == when) & key_follows
            elif rank_follows:
                later |= at == when
            query = query.where(later)
        order = (at.desc(), key.desc()) if newest_first else (at.asc(), key.asc())
        result = await self._session.execute(query.order_by(*order).limit(limit))
        return list(result.all()) if kind == "answer" else list(result.scalars())


ENTRY_RANK = {"question": 0, "answer": 1, "comment": 2, "message": 3}
