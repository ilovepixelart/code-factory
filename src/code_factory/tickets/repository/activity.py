"""Queries over a ticket's history, which `TicketRepository` carries as well."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.tickets.rules import FINDING_KINDS
from code_factory.tickets.tables import VISIBLE, TicketActivityRow, TicketRow


class ActivityQueries:
    """The append-only history of the tickets."""

    _session: AsyncSession

    async def moves_of(self, numbers: list[int]) -> list[TicketActivityRow]:
        """The `stage` records of the tickets, oldest first."""
        rows = await self._session.scalars(
            select(TicketActivityRow)
            .where(TicketActivityRow.ticket_number.in_(numbers), TicketActivityRow.kind == "stage")
            .order_by(TicketActivityRow.id)
        )
        return list(rows)

    async def latest_marks(
        self, numbers: list[int]
    ) -> tuple[list[TicketActivityRow], list[tuple[int, datetime]]]:
        """The newest `stage` and `archived` record of each ticket, and its newest record's time."""
        newest = await self._session.scalars(
            select(TicketActivityRow)
            .where(
                TicketActivityRow.ticket_number.in_(numbers),
                TicketActivityRow.kind.in_(("stage", "archived")),
            )
            .ext(distinct_on(TicketActivityRow.ticket_number, TicketActivityRow.kind))
            .order_by(
                TicketActivityRow.ticket_number,
                TicketActivityRow.kind,
                TicketActivityRow.id.desc(),
            )
        )
        last = await self._session.execute(
            select(TicketActivityRow.ticket_number, func.max(TicketActivityRow.at))
            .where(TicketActivityRow.ticket_number.in_(numbers))
            .group_by(TicketActivityRow.ticket_number)
        )
        return list(newest), [(number, at) for number, at in last]

    async def diagnoses(self) -> list[TicketActivityRow]:
        """Every diagnosis on every ticket, newest first."""
        rows = await self._session.scalars(
            select(TicketActivityRow)
            .where(TicketActivityRow.kind == "diagnosis")
            .order_by(TicketActivityRow.id.desc())
        )
        return list(rows)

    async def append_activity(
        self, number: int, record: tuple[datetime, str, str], data: dict[str, Any]
    ) -> TicketActivityRow:
        """Append one history record `(at, kind, by)`."""
        at, kind, by = record
        row = TicketActivityRow(ticket_number=number, at=at, kind=kind, by=by, data=data)
        self._session.add(row)
        await self._session.flush()
        return row

    async def kind_of_many(self, numbers: list[int], kind: str) -> list[TicketActivityRow]:
        """Every record of `kind` of these tickets, in the order they were written."""
        rows = await self._session.scalars(
            select(TicketActivityRow)
            .where(TicketActivityRow.ticket_number.in_(numbers), TicketActivityRow.kind == kind)
            .order_by(TicketActivityRow.id)
        )
        return list(rows)

    async def activity_of(
        self, number: int, kinds: list[str] | None, page: tuple[int, int | None, bool]
    ) -> list[TicketActivityRow]:
        """Up to `limit` records past the record `after`, by id; `page` is that triple."""
        limit, after, newest_first = page
        query = select(TicketActivityRow).where(TicketActivityRow.ticket_number == number)
        if kinds is not None:
            query = query.where(TicketActivityRow.kind.in_(kinds))
        if after is not None:
            beyond = TicketActivityRow.id < after if newest_first else TicketActivityRow.id > after
            query = query.where(beyond)
        order = TicketActivityRow.id.desc() if newest_first else TicketActivityRow.id
        return list(await self._session.scalars(query.order_by(order).limit(limit)))

    async def finding_ids(self, number: int) -> list[str]:
        """The ids of the ticket's findings, in the order they were recorded."""
        rows = await self._session.scalars(
            select(TicketActivityRow.data["id"].astext)
            .where(TicketActivityRow.ticket_number == number, TicketActivityRow.kind == "finding")
            .order_by(TicketActivityRow.id)
        )
        return list(rows)

    async def finding_trail(self, number: int) -> list[TicketActivityRow]:
        """The ticket's finding and review records, in the order they were written."""
        return await self.finding_trails([number])

    async def finding_trails(self, numbers: list[int]) -> list[TicketActivityRow]:
        """Finding and review records across these tickets, ordered by write."""
        rows = await self._session.scalars(
            select(TicketActivityRow)
            .where(
                TicketActivityRow.ticket_number.in_(numbers),
                TicketActivityRow.kind.in_(FINDING_KINDS),
            )
            .order_by(TicketActivityRow.id)
        )
        return list(rows)

    async def role_notes(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        ids: list[int] | None = None,
    ) -> list[TicketActivityRow]:
        """Authenticated review-role notes in a time window or with the given ids."""
        note = TicketActivityRow
        query = select(note).where(
            note.kind == "note", note.data["review_role"].astext.is_not(None)
        )
        if since is not None and until is not None:
            query = query.where(note.at >= since, note.at < until)
        if ids is not None:
            query = query.where(note.id.in_(ids))
        return list(await self._session.scalars(query))

    async def latest_coordinator_edit(self, number: int, name: str) -> TicketActivityRow | None:
        """The newest `coordinator_edit` of field `name` on the ticket."""
        return await self._session.scalar(
            select(TicketActivityRow)
            .where(
                TicketActivityRow.ticket_number == number,
                TicketActivityRow.kind == "coordinator_edit",
                TicketActivityRow.data["name"].astext == name,
            )
            .order_by(TicketActivityRow.id.desc())
            .limit(1)
        )

    async def count_activity(self, by: str, kind: str) -> int:
        """How many records of `kind` the actor `by` wrote."""
        count = await self._session.scalar(
            select(func.count())
            .select_from(TicketActivityRow)
            .join(TicketRow, TicketRow.number == TicketActivityRow.ticket_number)
            .where(
                TicketActivityRow.by == by,
                TicketActivityRow.kind == kind,
                VISIBLE,
            )
        )
        return count or 0
