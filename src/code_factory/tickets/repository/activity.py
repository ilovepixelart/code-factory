"""Queries over a ticket's history, which `TicketRepository` carries as well."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Text, cast, column, func, or_, select, true
from sqlalchemy.dialects.postgresql import ARRAY, distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

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

    async def latest_checks(
        self, heads: dict[int, str], excluded_codes: frozenset[int]
    ) -> list[TicketActivityRow]:
        """Read at most one check that judged each requested head, in one database call."""
        numbers, commits = zip(*heads.items(), strict=True)
        wanted = (
            func.unnest(cast(list(numbers), ARRAY(BigInteger)), cast(list(commits), ARRAY(Text)))
            .table_valued(column("number", BigInteger), column("head", Text))
            .render_derived(name="wanted")
        )
        row = TicketActivityRow
        code = row.data["exit_code"].astext
        newest = (
            select(row)
            .where(
                row.ticket_number == wanted.c.number,
                row.kind == "checks",
                or_(wanted.c.head == "", row.data["commit"].astext == wanted.c.head),
                func.jsonb_typeof(row.data["exit_code"]) == "number",
                code.op("~")(r"^-?[0-9]+$"),
                code.not_in(sorted(map(str, excluded_codes))),
            )
            .order_by(row.id.desc())
            .limit(1)
            .correlate(wanted)
            .lateral()
        )
        query = select(aliased(row, newest)).select_from(wanted.join(newest, true()))
        return list(await self._session.scalars(query))

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

    async def feed_of(self, number: int, limit: int) -> list[TicketActivityRow]:
        """The newest visible entries, plus the finish records needed to fold those runs."""
        row = TicketActivityRow
        start = aliased(row)
        run = func.coalesce(row.data["run"].astext, "")
        has_start = (
            select(start.id)
            .where(
                start.ticket_number == number,
                start.kind == "run.started",
                func.coalesce(start.data["run"].astext, "") == run,
            )
            .exists()
        )
        recent = await self._session.scalars(
            select(row)
            .where(row.ticket_number == number, or_(row.kind != "run.ended", ~has_start))
            .order_by(row.at.desc(), row.id.desc())
            .limit(limit)
        )
        visible = list(recent)
        runs = [
            str(item.data["run"])
            for item in visible
            if item.kind == "run.started" and item.data.get("run") not in (None, "")
        ]
        if runs:
            visible.extend(await self._run_finishes(number, runs))
        # The feed merger preserves this order for equal timestamps.
        return sorted(visible, key=lambda item: item.id)

    async def _run_finishes(self, number: int, runs: Sequence[str]) -> list[TicketActivityRow]:
        row = TicketActivityRow
        run = row.data["run"].astext
        newest = await self._session.scalars(
            select(row)
            .where(row.ticket_number == number, row.kind == "run.ended", run.in_(runs))
            .ext(distinct_on(run))
            .order_by(run, row.at.desc(), row.id.desc())
        )
        return list(newest)

    async def evidence_of(self, number: int) -> list[TicketActivityRow]:
        """Stage transitions and the check, conflict and capture records that determine state."""
        row = TicketActivityRow
        latest_by_kind = (
            select(row.id)
            .where(row.ticket_number == number, row.kind.in_(("checks", "capture")))
            .ext(distinct_on(row.kind))
            .order_by(row.kind, row.id.desc())
        )
        latest_conflict = (
            select(row.id)
            .where(
                row.ticket_number == number,
                row.kind.in_(("branch_conflict", "branch_conflict_cleared")),
            )
            .order_by(row.id.desc())
            .limit(1)
        )
        capture_tree = (
            select(func.coalesce(row.data["tree"].astext, ""))
            .where(row.ticket_number == number, row.kind == "capture")
            .order_by(row.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        latest_answers = (
            select(row.id)
            .where(
                row.ticket_number == number,
                row.kind.in_(("capture_approved", "capture_changes")),
                func.coalesce(row.data["tree"].astext, "") == capture_tree,
            )
            .ext(distinct_on(row.kind))
            .order_by(row.kind, row.id.desc())
        )
        rows = await self._session.scalars(
            select(row)
            .where(
                row.ticket_number == number,
                or_(
                    row.kind.in_(("created", "stage")),
                    row.id.in_(latest_by_kind),
                    row.id.in_(latest_conflict),
                    row.id.in_(latest_answers),
                ),
            )
            .order_by(row.id)
        )
        return list(rows)

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
