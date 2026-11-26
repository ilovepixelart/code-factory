"""Queries over the delivery tables. Every method runs in the session it is given."""

from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.delivery.models import DeliveryEvent, PullReading, PullView
from code_factory.delivery.rules import entered_since, ticket_id, ticket_number
from code_factory.delivery.tables import EventRow, IntakeRow, PollRow, PullRow

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

    async def all_pulls(self) -> list[PullView]:
        """Every recorded pull request."""
        rows = await self._session.scalars(select(PullRow).order_by(PullRow.ticket_number))
        return [_view(row) for row in rows]

    async def first_at(self, kinds: tuple[str, ...]) -> dict[tuple[str, str], datetime]:
        """The first event of each (ticket, url) among `kinds`."""
        rows = await self._session.execute(
            select(EventRow.ticket_number, EventRow.url, func.min(EventRow.at))
            .where(EventRow.kind.in_(kinds))
            .group_by(EventRow.ticket_number, EventRow.url)
        )
        return {(ticket_id(number), url): at for number, url, at in rows}

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

    async def set_shipped(self, ticket: str, head: str) -> None:
        """The commit the board shipped to the recorded pull request."""
        await self._session.execute(
            update(PullRow)
            .where(PullRow.ticket_number == ticket_number(ticket))
            .values(shipped_head=head)
        )

    async def set_state(self, ticket: str, state: str) -> None:
        """Mark the recorded pull request merged or closed."""
        await self._session.execute(
            update(PullRow)
            .where(PullRow.ticket_number == ticket_number(ticket))
            .values(state=state)
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
        return done.scalar_one_or_none() is not None

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
