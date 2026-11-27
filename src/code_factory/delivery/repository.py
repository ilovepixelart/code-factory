"""Queries over the delivery tables. Every method runs in the session it is given."""

from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from code_factory.delivery.models import DeliveryEvent, PullHistory, PullReading, PullView
from code_factory.delivery.rules import entered_since, ticket_id, ticket_number
from code_factory.delivery.tables import EventRow, IntakeRow, PollRow, PullHistoryRow, PullRow

POLL_EVERY = timedelta(seconds=60)


def _view(row: PullRow) -> PullView:
    return PullView(
        ticket_id=ticket_id(row.ticket_number),
        repository=row.repository,
        url=row.url,
        state=row.state,  # ty: ignore[invalid-argument-type]
        review=row.review,
        ci=row.ci,  # ty: ignore[invalid-argument-type]
        other_ci=row.other_ci,
        own_pending=row.own_pending,
        head=row.head,
        base=row.base,
        draft=row.draft,
        conflict=row.conflict,
        reviewed=row.reviewed,
        merge_state=row.merge_state,
        additions=row.additions,
        deletions=row.deletions,
        changed_files=row.changed_files,
        created_on_host=row.created_on_host,
        updated_on_host=row.updated_on_host,
        merged_on_host=row.merged_on_host,
        first_review_at=row.first_review_at,
        shipped_head=row.shipped_head,
        read_at=row.read_at,
        since=row.since,
    )


def _event(row: EventRow) -> DeliveryEvent:
    return DeliveryEvent(
        id=row.id,
        ticket_id=ticket_id(row.ticket_number),
        kind=row.kind,  # ty: ignore[invalid-argument-type]
        url=row.url,
        head=row.head,
        reason=row.reason,
        by=row.by,
        from_base=row.from_base,
        to_base=row.to_base,
        retry_at=row.retry_at,
        at=row.at,
    )


class DeliveryRepository:
    """Pull requests, events, polls and intake."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def pulls(self, ids: Iterable[str]) -> dict[str, PullView]:
        """The recorded pull requests of the tickets, by id."""
        numbers = [ticket_number(i) for i in ids]
        rows = await self._session.scalars(
            select(PullRow).where(PullRow.ticket_number.in_(numbers))
        )
        return {view.ticket_id: view for view in map(_view, rows)}

    async def open_pulls(self) -> list[PullView]:
        """Every recorded open pull request."""
        rows = await self._session.scalars(select(PullRow).where(PullRow.state == "open"))
        return [_view(row) for row in rows]

    async def history(self, since: datetime, until: datetime) -> list[PullHistory]:
        """Pulls opened or merged in the window, with the lifetime count for each ticket."""
        pull = PullHistoryRow
        related = aliased(PullHistoryRow)
        count = (
            select(func.count())
            .select_from(related)
            .where(related.ticket_number == pull.ticket_number)
            .scalar_subquery()
        )
        result = await self._session.execute(
            select(pull, count)
            .where(
                or_(
                    and_(pull.opened_at >= since, pull.opened_at < until),
                    and_(pull.merged_at >= since, pull.merged_at < until),
                )
            )
            .order_by(pull.opened_at, pull.url)
        )
        return [
            PullHistory(
                ticket_id=ticket_id(row.ticket_number),
                repository=row.repository,
                url=row.url,
                state=row.state,  # ty: ignore[invalid-argument-type]
                opened_at=row.opened_at,
                merged_at=row.merged_at,
                closed_at=row.closed_at,
                first_review_at=row.first_review_at,
                changed_lines=row.changed_lines,
                ticket_pulls=total,
            )
            for row, total in result
        ]

    async def known_merge(self, ticket: str, url: str) -> bool:
        """Whether this exact pull request recorded a merge for the named ticket."""
        pull = PullHistoryRow
        return (
            await self._session.scalar(
                select(pull.url).where(
                    pull.ticket_number == ticket_number(ticket),
                    pull.url == url,
                    pull.merged_at.is_not(None),
                )
            )
            is not None
        )

    async def known_urls(self, repository: str) -> set[str]:
        """The pull request urls recorded for the repository."""
        rows = await self._session.scalars(
            select(PullRow.url).where(PullRow.repository == repository)
        )
        return set(rows)

    async def record_pull(
        self, ticket: str, repository: str, url: str, reading: PullReading, now: datetime
    ) -> None:
        """Write what GitHub says of the ticket's pull request; `since` moves only on a change."""
        number = ticket_number(ticket)
        row = await self._session.get(PullRow, number)
        last = (row.state, row.ci, row.head, row.since) if row and row.url == url else None
        since = entered_since(last, reading, now)  # ty: ignore[invalid-argument-type]
        values = reading.model_dump() | {"url": url, "read_at": now, "since": since}
        if row is None:
            self._session.add(PullRow(ticket_number=number, repository=repository, **values))
        else:
            if row.url != url:
                values["shipped_head"] = ""
            for name, value in values.items():
                setattr(row, name, value)
        await self._session.flush()
        if url:
            await self._remember_pull(number, repository, url, reading, now)

    async def _remember_pull(
        self, number: int, repository: str, url: str, reading: PullReading, now: datetime
    ) -> None:
        pull = PullHistoryRow
        changed = (
            reading.additions + reading.deletions
            if reading.additions is not None and reading.deletions is not None
            else None
        )
        statement = pg_insert(pull).values(
            url=url,
            ticket_number=number,
            repository=repository,
            state=reading.state,
            opened_at=reading.created_on_host or now,
            merged_at=reading.merged_on_host or (now if reading.state == "merged" else None),
            closed_at=now if reading.state == "closed" else None,
            first_review_at=reading.first_review_at,
            changed_lines=changed,
        )
        incoming = statement.excluded
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[pull.url],
                set_={
                    "state": case((pull.merged_at.is_not(None), "merged"), else_=incoming.state),
                    "opened_at": reading.created_on_host or pull.opened_at,
                    "merged_at": (
                        reading.merged_on_host or func.coalesce(pull.merged_at, incoming.merged_at)
                    ),
                    "closed_at": case(
                        (
                            incoming.state == "closed",
                            func.coalesce(pull.closed_at, incoming.closed_at),
                        ),
                        (incoming.state == "", pull.closed_at),
                        else_=None,
                    ),
                    "first_review_at": func.least(pull.first_review_at, incoming.first_review_at),
                    "changed_lines": func.coalesce(incoming.changed_lines, pull.changed_lines),
                },
            )
        )

    async def set_shipped(self, ticket: str, head: str) -> None:
        """The commit the board shipped to the recorded pull request."""
        await self._session.execute(
            update(PullRow)
            .where(PullRow.ticket_number == ticket_number(ticket))
            .values(shipped_head=head)
        )

    async def _mark_merged(self, ticket: str, url: str, at: datetime) -> None:
        """Mark this pull merged, even if its ticket now points to a replacement."""
        number = ticket_number(ticket)
        await self._session.execute(
            update(PullRow)
            .where(PullRow.ticket_number == number, PullRow.url == url)
            .values(state="merged")
        )
        pull = PullHistoryRow
        await self._session.execute(
            update(pull)
            .where(pull.ticket_number == number, pull.url == url)
            .values(state="merged", merged_at=func.least(pull.merged_at, at), closed_at=None)
        )

    async def record(self, event: DeliveryEvent) -> bool:
        """Append the event; false when its once-only index already holds it."""
        values = event.model_dump(exclude={"id", "ticket_id"})
        done = await self._session.execute(
            pg_insert(EventRow)
            .values(ticket_number=ticket_number(event.ticket_id), **values)
            .on_conflict_do_nothing()
            .returning(EventRow.id)
        )
        recorded = done.scalar_one_or_none() is not None
        if event.kind == "merged_pull_request" and event.url:
            await self._mark_merged(event.ticket_id, event.url, event.at)
        elif event.kind == "pull_request" and event.url:
            pull = PullHistoryRow
            await self._session.execute(
                update(pull)
                .where(pull.ticket_number == ticket_number(event.ticket_id), pull.url == event.url)
                .values(opened_at=func.least(pull.opened_at, event.at))
            )
        return recorded

    async def events(self, ids: Iterable[str]) -> dict[str, list[DeliveryEvent]]:
        """Each ticket's events, oldest first."""
        numbers = [ticket_number(i) for i in ids]
        rows = await self._session.scalars(
            select(EventRow).where(EventRow.ticket_number.in_(numbers)).order_by(EventRow.id)
        )
        found: dict[str, list[DeliveryEvent]] = {}
        for row in rows:
            event = _event(row)
            found.setdefault(event.ticket_id, []).append(event)
        return found

    async def claim_poll(self, key: str, now: datetime) -> bool:
        """Whether this caller lists `key` now: at most once a minute, one winner."""
        cutoff = now - POLL_EVERY
        claimed = await self._session.execute(
            pg_insert(PollRow)
            .values(key=key, listed_at=now)
            .on_conflict_do_update(
                index_elements=[PollRow.key],
                set_={"listed_at": now},
                where=PollRow.listed_at <= cutoff,
            )
            .returning(PollRow.key)
        )
        return claimed.scalar_one_or_none() is not None

    async def imported(self, repository: str) -> set[str]:
        """The sources already imported into the repository."""
        rows = await self._session.scalars(
            select(IntakeRow.source).where(IntakeRow.repository == repository)
        )
        return set(rows)

    async def imported_tickets(self, repository: str) -> dict[str, str]:
        """The ticket each source imported into the repository became, by source."""
        rows = await self._session.execute(
            select(IntakeRow.source, IntakeRow.ticket_id).where(IntakeRow.repository == repository)
        )
        return dict(rows.all())

    async def record_intake(
        self, repository: str, source: str, tracker: str, ticket: str, now: datetime
    ) -> bool:
        """Remember that the source became the ticket; false when it was already imported."""
        done = await self._session.execute(
            pg_insert(IntakeRow)
            .values(
                repository=repository,
                source=source,
                tracker=tracker,
                ticket_id=ticket,
                imported_at=now,
            )
            .on_conflict_do_nothing()
            .returning(IntakeRow.source)
        )
        return done.scalar_one_or_none() is not None
