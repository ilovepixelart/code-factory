"""A ticket's history: append-only records, read in the order they were written."""

from collections.abc import Callable, Mapping
from datetime import datetime

from code_factory.platform.db import UnitOfWork
from code_factory.tickets.models import (
    Activity,
    ActivityEntry,
    ActivityMarks,
    ActivityPage,
    NewActivity,
    NoteKind,
)
from code_factory.tickets.repository import TicketRepository
from code_factory.tickets.rules import (
    check_kind,
    check_note,
    describe,
    ticket_id,
    ticket_number,
)
from code_factory.tickets.service.common import not_found, utc_now
from code_factory.tickets.tables import TicketActivityRow

PAGE_DEFAULT = 25
PAGE_MAX = 100
_ALL = 1_000_000


def to_activity(row: TicketActivityRow) -> Activity:
    """A record's answer."""
    return Activity(
        id=row.id,
        ticket_id=ticket_id(row.ticket_number),
        at=row.at,
        kind=row.kind,
        by=row.by,
        data=row.data,
    )


def _cursor(text: str | None) -> int | None:
    return int(text) if text is not None and text.isdigit() else None


def _entry(row: TicketActivityRow) -> ActivityEntry:
    return ActivityEntry(
        at=row.at,
        kind=row.kind,
        by=row.by,
        sentence=describe(row.kind, row.data),
        data=row.data,
        id=row.id,
    )


class ActivityService:
    """Append to and read a ticket's history."""

    def __init__(self, uow: UnitOfWork, clock: Callable[[], datetime] = utc_now) -> None:
        self._uow = uow
        self._clock = clock

    async def append(self, ticket: str, record: NewActivity, *, by: str) -> Activity:
        """Append one record to the ticket's history; `record.at` defaults to now."""
        number = ticket_number(ticket)
        kind = check_kind(record.kind)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number) is None:
                raise not_found(number)
            at = record.at or self._clock()
            row = await tickets.append_activity(number, (at, kind, by), record.data)
            return to_activity(row)

    async def list_activity(
        self,
        ticket: str,
        *,
        kinds: list[str] | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        newest_first: bool = False,
    ) -> ActivityPage:
        """The ticket's records, oldest first unless `newest_first`.

        At most `limit` (25 by default, 100 at most); `next_cursor` continues after the last one.
        """
        number = ticket_number(ticket)
        size = min(max(limit or PAGE_DEFAULT, 1), PAGE_MAX)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number) is None:
                raise not_found(number)
            rows = await tickets.activity_of(
                number, kinds, (size + 1, _cursor(cursor), newest_first)
            )
        items = [to_activity(row) for row in rows[:size]]
        more = len(rows) > size
        return ActivityPage(items=items, next_cursor=str(items[-1].id) if more else None)

    async def record_note(
        self, ticket: str, text: str, kind: NoteKind, *, by: str, review_role: str = ""
    ) -> Activity:
        """A note (or a diagnosis) on the ticket's history under the actor's name."""
        note = check_note(text)
        data = {"text": note}
        if kind == "note" and review_role:
            data["review_role"] = review_role
        return await self.append(ticket, NewActivity(kind=kind, data=data), by=by)

    async def count_authored(self, by: str, kind: str) -> int:
        """How many records of `kind` the actor wrote on every ticket; `created` counts tickets."""
        async with self._uow() as session:
            return await TicketRepository(session).count_activity(by, kind)

    async def entries(self, ticket: str) -> list[ActivityEntry]:
        """Every record of the ticket as a feed entry, oldest first, to merge with other feeds."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number) is None:
                raise not_found(number)
            rows = await tickets.activity_of(number, None, (_ALL, None, False))
        return [_entry(row) for row in rows]

    async def feed_entries(self, ticket: str, limit: int) -> list[ActivityEntry]:
        """Up to `limit` visible entries, with their run finishes for folding."""
        async with self._uow() as session:
            rows = await TicketRepository(session).feed_of(ticket_number(ticket), limit)
        return [_entry(row) for row in rows]

    async def evidence_entries(self, ticket: str) -> list[ActivityEntry]:
        """Stage and evidence records for a ticket that has already been read."""
        async with self._uow() as session:
            rows = await TicketRepository(session).evidence_of(ticket_number(ticket))
        return [_entry(row) for row in rows]

    async def records_of(self, tickets: list[str], kind: str) -> dict[str, list[Activity]]:
        """Each ticket's records of `kind`, oldest first, in one read.

        A ticket with none, or an id that names no ticket, is absent from the answer.
        """
        numbers = [ticket_number(t) for t in tickets]
        if not numbers:
            return {}
        async with self._uow() as session:
            rows = await TicketRepository(session).kind_of_many(numbers, kind)
        found: dict[str, list[Activity]] = {}
        for row in rows:
            found.setdefault(ticket_id(row.ticket_number), []).append(to_activity(row))
        return found

    async def latest_checks(
        self, heads: Mapping[str, str], excluded_codes: frozenset[int]
    ) -> dict[str, Activity]:
        """One matching check per ticket, with an empty head matching any commit."""
        if not heads:
            return {}
        numbers = {ticket_number(ticket): head for ticket, head in heads.items()}
        async with self._uow() as session:
            rows = await TicketRepository(session).latest_checks(numbers, excluded_codes)
        return {ticket_id(row.ticket_number): to_activity(row) for row in rows}

    async def latest_marks(self, tickets: list[str]) -> dict[str, ActivityMarks]:
        """When each ticket last moved, was archived and was touched, in one read.

        A ticket with no record is absent from the answer.
        """
        numbers = [ticket_number(t) for t in tickets]
        if not numbers:
            return {}
        async with self._uow() as session:
            newest, last = await TicketRepository(session).latest_marks(numbers)
        marks = {number: ActivityMarks(last_at=at) for number, at in last}
        for row in newest:
            if row.kind == "stage":
                marks[row.ticket_number].moved_to = str(row.data.get("to", ""))
                marks[row.ticket_number].moved_at = row.at
            else:
                marks[row.ticket_number].archived_at = row.at
        return {ticket_id(number): mark for number, mark in marks.items()}
