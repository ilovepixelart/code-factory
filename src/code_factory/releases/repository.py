"""Queries over the release tables. Every method runs in the session it is given."""

from collections.abc import Sequence
from datetime import datetime
from typing import cast

from sqlalchemy import Text, any_, func, literal, select, update
from sqlalchemy.dialects.postgresql import ARRAY, insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.releases.tables import ReleaseRow, ReleaseTicketRow


class ReleaseRepository:
    """The releases of the tracked repositories and the tickets they name."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_draft(
        self, repository: str, version: str, notes: str, at: datetime
    ) -> ReleaseRow | None:
        """Insert a draft; `None` when the version exists, with no pre-read to race against."""
        statement = (
            insert(ReleaseRow)
            .values(repository=repository, version=version, notes=notes, drafted_at=at)
            .on_conflict_do_nothing(index_elements=["repository", "version"])
            .returning(ReleaseRow)
        )
        return await self._session.scalar(statement)

    async def find(
        self, repository: str, version: str, *, for_update: bool = False
    ) -> ReleaseRow | None:
        """The release `version` of `repository`, locked against concurrent writers when asked."""
        query = select(ReleaseRow).where(
            ReleaseRow.repository == repository, ReleaseRow.version == version
        )
        if for_update:
            query = query.with_for_update()
        return await self._session.scalar(query)

    async def with_tickets(
        self, repository: str | None, version: str | None = None
    ) -> list[tuple[ReleaseRow, list[str]]]:
        """Releases with the ticket ids each names, read in one statement so they agree.

        All of them, those of one repository, or the one `version` of it; in no particular order.
        """
        named = func.array_agg(ReleaseTicketRow.ticket_id).filter(
            ReleaseTicketRow.ticket_id.is_not(None)
        )
        query = (
            select(ReleaseRow, named)
            .outerjoin(ReleaseTicketRow, ReleaseTicketRow.release_id == ReleaseRow.id)
            .group_by(ReleaseRow.id)
        )
        if repository is not None:
            query = query.where(ReleaseRow.repository == repository)
        if version is not None:
            query = query.where(ReleaseRow.version == version)
        return [(row, list(ids or [])) for row, ids in await self._session.execute(query)]

    async def update_notes(self, repository: str, version: str, notes: str) -> ReleaseRow | None:
        """Replace the notes of a draft; `None` when there is no such draft."""
        statement = (
            update(ReleaseRow)
            .where(
                ReleaseRow.repository == repository,
                ReleaseRow.version == version,
                ReleaseRow.published_at.is_(None),
            )
            .values(notes=notes)
            .returning(ReleaseRow)
        )
        return await self._session.scalar(statement)

    async def publish(
        self, repository: str, version: str, at: datetime, ticket_ids: Sequence[str]
    ) -> ReleaseRow | None:
        """Publish a draft and record the tickets it names; `None` when there is no such draft."""
        statement = (
            update(ReleaseRow)
            .where(
                ReleaseRow.repository == repository,
                ReleaseRow.version == version,
                ReleaseRow.published_at.is_(None),
            )
            .values(published_at=at)
            .returning(ReleaseRow)
        )
        row = await self._session.scalar(statement)
        if row is not None and ticket_ids:
            await self._session.execute(
                insert(ReleaseTicketRow),
                [{"release_id": row.id, "ticket_id": ticket_id} for ticket_id in ticket_ids],
            )
        return row

    async def set_tag_commit(self, repository: str, version: str, commit: str) -> ReleaseRow | None:
        """Record the commit a published release is tagged on, once.

        `None` when the release is a draft or is recorded on another commit.
        """
        statement = (
            update(ReleaseRow)
            .where(
                ReleaseRow.repository == repository,
                ReleaseRow.version == version,
                ReleaseRow.published_at.is_not(None),
                ReleaseRow.tag_commit.is_(None) | (ReleaseRow.tag_commit == commit),
            )
            .values(tag_commit=commit)
            .returning(ReleaseRow)
        )
        return await self._session.scalar(statement)

    async def set_tagged(self, repository: str, version: str, at: datetime) -> ReleaseRow | None:
        """Record that the tag reached origin, keeping the first time; `None` with no commit."""
        statement = (
            update(ReleaseRow)
            .where(
                ReleaseRow.repository == repository,
                ReleaseRow.version == version,
                ReleaseRow.tag_commit.is_not(None),
            )
            .values(tagged_at=func.coalesce(ReleaseRow.tagged_at, at))
            .returning(ReleaseRow)
        )
        return await self._session.scalar(statement)

    async def tickets_of(self, release_ids: Sequence[int]) -> dict[int, list[str]]:
        """The ticket ids each release names, unordered."""
        named: dict[int, list[str]] = {release_id: [] for release_id in release_ids}
        rows = await self._session.execute(
            select(ReleaseTicketRow.release_id, ReleaseTicketRow.ticket_id).where(
                ReleaseTicketRow.release_id.in_(release_ids)
            )
        )
        for release_id, ticket_id in rows:
            named[release_id].append(ticket_id)
        return named

    async def named_in_published(self, repository: str) -> set[str]:
        """Every ticket id a published release of the repository names."""
        rows = await self._session.scalars(
            select(ReleaseTicketRow.ticket_id)
            .join(ReleaseRow, ReleaseRow.id == ReleaseTicketRow.release_id)
            .where(ReleaseRow.repository == repository, ReleaseRow.published_at.is_not(None))
        )
        return set(rows)

    async def naming(self, refs: Sequence[tuple[str, str]]) -> list[tuple[str, str, str, datetime]]:
        """`(repository, ticket id, version, published_at)` for the refs a published release names.

        One statement whatever the number of refs: the ids and repositories travel as two arrays
        that narrow the rows (the ticket id index serves it) and the pairs are matched here.
        The earliest published release comes first.
        """
        wanted = set(refs)
        statement = (
            select(
                ReleaseRow.repository,
                ReleaseTicketRow.ticket_id,
                ReleaseRow.version,
                ReleaseRow.published_at,
            )
            .join(ReleaseTicketRow, ReleaseTicketRow.release_id == ReleaseRow.id)
            .where(
                ReleaseTicketRow.ticket_id == any_(literal([t for _, t in wanted], ARRAY(Text))),
                ReleaseRow.repository == any_(literal([r for r, _ in wanted], ARRAY(Text))),
                ReleaseRow.published_at.is_not(None),
            )
            .order_by(ReleaseRow.published_at, ReleaseRow.id)
        )
        return [
            (
                repository,
                ticket_id,
                version,
                cast("datetime", published_at),
            )  # the query keeps published
            for repository, ticket_id, version, published_at in await self._session.execute(
                statement
            )
            if (repository, ticket_id) in wanted
        ]
