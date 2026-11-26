"""Queries over the tickets, their links, pull requests and activity."""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, delete, func, or_, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.db import lock_until_commit
from code_factory.platform.errors import ConflictError, UnavailableError
from code_factory.tickets.models import PullRequest, PullRequestState, TicketFilter
from code_factory.tickets.repository.activity import ActivityQueries
from code_factory.tickets.tables import (
    VISIBLE,
    TicketActivityRow,
    TicketDocumentRow,
    TicketLinkRow,
    TicketPullRequestRow,
    TicketRow,
)

Links = dict[str, list[int]]
SOURCE_INDEX = "uq_tickets_repository_source"


def _source_conflict(error: IntegrityError, source: str) -> ConflictError | None:
    """The refusal for a source another ticket of the repository holds; `None` for any other."""
    if SOURCE_INDEX not in str(error.orig):
        return None
    msg = f"a ticket from {source} exists in this repository; open it instead of filing another"
    return ConflictError(msg)


def _lock_timeout(error: DBAPIError) -> bool:
    return bool(getattr(error.orig, "sqlstate", None) == "55P03") or "lock timeout" in str(
        error.orig
    )


_ANCESTORS = text(
    """
    WITH RECURSIVE up(number) AS (
        SELECT linked_number FROM ticket_links WHERE ticket_number = :number AND kind = 'parent'
        UNION
        SELECT l.linked_number FROM ticket_links l JOIN up ON l.ticket_number = up.number
        WHERE l.kind = 'parent'
    )
    SELECT number FROM up
    """
)


class TicketRepository(ActivityQueries):
    """Tickets, their links and their pull requests."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, values: dict[str, Any]) -> TicketRow:
        """Insert a ticket; its number comes from the sequence."""
        row = TicketRow(**values)
        self._session.add(row)
        await self.flush(str(values.get("source", "")))
        return row

    async def flush(self, source: str = "") -> None:
        """Write the pending changes, so a query in the same unit of work reads them.

        `source` is the one being written, named when another ticket holds it (`ConflictError`).
        """
        try:
            await self._session.flush()
        except IntegrityError as error:
            refusal = _source_conflict(error, source)
            if refusal is None:
                raise
            raise refusal from error

    async def find(
        self, number: int, *, for_update: bool = False, trashed: bool = False
    ) -> TicketRow | None:
        """The ticket (a trashed one when `trashed`), locked against writers when `for_update`."""
        query = select(TicketRow).where(TicketRow.number == number, TicketRow.trashed.is_(trashed))
        if for_update:
            query = query.with_for_update()
        return await self._session.scalar(query)

    async def delete_with_history(self, number: int) -> None:
        """Remove the ticket and its history; the database allows it for a scratch ticket only."""
        await self._session.execute(
            delete(TicketActivityRow).where(TicketActivityRow.ticket_number == number)
        )
        await self._session.execute(delete(TicketRow).where(TicketRow.number == number))

    async def find_by_source(self, repository: str, source: str) -> TicketRow | None:
        """The ticket of `repository` filed from `source`."""
        return await self._session.scalar(
            select(TicketRow).where(
                TicketRow.repository == repository,
                TicketRow.source == source,
                TicketRow.trashed.is_(False),
            )
        )

    async def sources_of(self, repository: str) -> list[str]:
        """Every source a ticket of the repository was filed from."""
        rows = await self._session.scalars(
            select(TicketRow.source).where(
                TicketRow.repository == repository,
                TicketRow.source != "",
                VISIBLE,
            )
        )
        return list(rows)

    async def find_by_branch(self, repository: str, branch: str) -> TicketRow | None:
        """The ticket of `repository` that holds `branch`."""
        return await self._session.scalar(
            select(TicketRow).where(
                TicketRow.repository == repository,
                TicketRow.branch == branch,
                TicketRow.trashed.is_(False),
            )
        )

    async def merged_among(self, repository: str, numbers: list[int]) -> set[int]:
        """The numbers among `numbers` of tickets in `repository` whose work is merged."""
        merged_pull = select(TicketPullRequestRow.ticket_number).where(
            TicketPullRequestRow.state == PullRequestState.MERGED.value
        )
        rows = await self._session.scalars(
            select(TicketRow.number).where(
                TicketRow.repository == repository,
                TicketRow.number.in_(numbers),
                TicketRow.trashed.is_(False),
                or_(TicketRow.merged.is_(True), TicketRow.number.in_(merged_pull)),
            )
        )
        return set(rows)

    async def open_titles(self, repository: str) -> list[tuple[int, str]]:
        """`(number, title)` of each ticket of the repository neither archived nor merged."""
        merged_pull = select(TicketPullRequestRow.ticket_number).where(
            TicketPullRequestRow.state == PullRequestState.MERGED.value
        )
        rows = await self._session.execute(
            select(TicketRow.number, TicketRow.title)
            .where(
                TicketRow.repository == repository,
                TicketRow.archived.is_(False),
                TicketRow.merged.is_(False),
                VISIBLE,
                TicketRow.number.not_in(merged_pull),
            )
            .order_by(TicketRow.number)
        )
        return [(number, title) for number, title in rows.all()]

    async def repositories(self) -> list[str]:
        """The repositories that hold a ticket on the board, by name."""
        rows = await self._session.scalars(
            select(TicketRow.repository).where(VISIBLE).distinct().order_by(TicketRow.repository)
        )
        return list(rows)

    async def lock_repositories(self, names: list[str], wait: float) -> None:
        """Hold each repository's ticket writes to this transaction, in name order.

        Waits at most `wait` seconds for each; a longer wait is `UnavailableError`.
        """
        milliseconds = max(int(wait * 1000), 1)
        await self._session.execute(
            select(func.set_config("lock_timeout", str(milliseconds), True))
        )
        try:
            for name in sorted(set(names)):
                await lock_until_commit(self._session, f"tickets:{name}")
        except DBAPIError as error:
            if not _lock_timeout(error):
                raise
            raise UnavailableError("the board is busy; try again") from error

    async def link_graph(self, repository: str) -> list[tuple[int, int | None]]:
        """`(number, parent number or None)` of each ticket on the board of the repository."""
        parent = and_(
            TicketLinkRow.ticket_number == TicketRow.number, TicketLinkRow.kind == "parent"
        )
        rows = await self._session.execute(
            select(TicketRow.number, TicketLinkRow.linked_number)
            .outerjoin(TicketLinkRow, parent)
            .where(TicketRow.repository == repository, VISIBLE)
            .order_by(TicketRow.number)
        )
        return [(number, linked) for number, linked in rows.all()]

    async def set_ranks(self, repository: str, ranks: dict[int, int]) -> None:
        """Set each ticket's rank; a number that is no ticket of the repository is skipped."""
        for number, rank in ranks.items():
            await self._session.execute(
                update(TicketRow)
                .where(
                    TicketRow.number == number,
                    TicketRow.repository == repository,
                    TicketRow.trashed.is_(False),
                )
                .values(rank=rank)
            )

    async def search_documents(
        self, repository: str, words: list[str], limit: int
    ) -> list[TicketDocumentRow]:
        """The repository's documents that hold every word, ignoring case, by ticket and name.

        A word is matched as text: `%` and `_` in it mean themselves.
        """
        query = (
            select(TicketDocumentRow)
            .join(TicketRow, TicketRow.number == TicketDocumentRow.ticket_number)
            .where(TicketRow.repository == repository, VISIBLE)
        )
        for word in words:
            query = query.where(TicketDocumentRow.body.icontains(word, autoescape=True))
        query = query.order_by(TicketDocumentRow.ticket_number, TicketDocumentRow.name).limit(limit)
        return list(await self._session.scalars(query))

    async def flow_rows(self, repository: str, numbers: list[int] | None) -> list[TicketRow]:
        """The repository's tickets (archived too), or those of `numbers`, by number."""
        query = select(TicketRow).where(TicketRow.repository == repository, VISIBLE)
        if numbers is not None:
            query = query.where(TicketRow.number.in_(numbers))
        return list(await self._session.scalars(query.order_by(TicketRow.number)))

    async def missing(self, numbers: Iterable[int]) -> list[int]:
        """The numbers among `numbers` that are no ticket, in the order given."""
        wanted = list(dict.fromkeys(numbers))
        if not wanted:
            return []
        found = set(
            await self._session.scalars(
                select(TicketRow.number).where(
                    TicketRow.number.in_(wanted), TicketRow.trashed.is_(False)
                )
            )
        )
        return [number for number in wanted if number not in found]

    async def ancestors(self, number: int) -> set[int]:
        """Every ticket above `number` through its parents."""
        rows = await self._session.execute(_ANCESTORS, {"number": number})
        return {row[0] for row in rows}

    async def links_of(self, numbers: list[int]) -> dict[int, Links]:
        """Each ticket's links by kind, in the order they were written."""
        rows = await self._session.scalars(
            select(TicketLinkRow)
            .where(TicketLinkRow.ticket_number.in_(numbers))
            .order_by(TicketLinkRow.ticket_number, TicketLinkRow.kind, TicketLinkRow.position)
        )
        links: dict[int, Links] = {number: {} for number in numbers}
        for row in rows:
            links[row.ticket_number].setdefault(row.kind, []).append(row.linked_number)
        return links

    async def linking_to(self, number: int) -> list[int]:
        """Tickets that name this number as their parent or blocker."""
        return list(
            await self._session.scalars(
                select(TicketLinkRow.ticket_number).where(
                    TicketLinkRow.linked_number == number,
                    TicketLinkRow.kind.in_(("parent", "blocked_by")),
                )
            )
        )

    async def replace_links(self, number: int, kind: str, linked: list[int]) -> None:
        """Make `linked` the ticket's links of `kind`."""
        await self._session.execute(
            delete(TicketLinkRow).where(
                TicketLinkRow.ticket_number == number, TicketLinkRow.kind == kind
            )
        )
        self._session.add_all(
            TicketLinkRow(ticket_number=number, kind=kind, linked_number=other, position=index)
            for index, other in enumerate(dict.fromkeys(linked))
        )
        await self._session.flush()

    async def pull_requests_of(self, numbers: list[int]) -> dict[int, PullRequest]:
        """The pull request of each ticket that has one."""
        rows = await self._session.scalars(
            select(TicketPullRequestRow).where(TicketPullRequestRow.ticket_number.in_(numbers))
        )
        return {
            row.ticket_number: PullRequest(number=row.number, state=row.state, url=row.url)
            for row in rows
        }

    async def put_pull_request(self, number: int, pull: PullRequest, at: datetime) -> None:
        """Record the ticket's pull request, replacing the one it had."""
        await self.remove_pull_request(number)
        self._session.add(
            TicketPullRequestRow(
                ticket_number=number,
                number=pull.number,
                state=pull.state.value,
                url=pull.url,
                updated_at=at,
            )
        )
        await self._session.flush()

    async def remove_pull_request(self, number: int) -> None:
        """Forget the ticket's pull request."""
        await self._session.execute(
            delete(TicketPullRequestRow).where(TicketPullRequestRow.ticket_number == number)
        )

    async def select(
        self, where: TicketFilter, parent: int | None, numbers: list[int] | None = None
    ) -> list[TicketRow]:
        """The tickets `where` selects (all but its column), in board order.

        Board order: a rank first (1 before 2), unranked (0) after every ranked one, then the
        number.
        """
        query = select(TicketRow).where(VISIBLE)
        if numbers is not None:
            query = query.where(TicketRow.number.in_(numbers))
        if where.repository is not None:
            query = query.where(TicketRow.repository == where.repository)
        if where.archived is not None:
            query = query.where(TicketRow.archived.is_(where.archived))
        if where.label is not None:
            query = query.where(TicketRow.labels.contains([where.label]))
        if parent is not None:
            query = query.where(
                TicketRow.number.in_(
                    select(TicketLinkRow.ticket_number).where(
                        TicketLinkRow.kind == "parent", TicketLinkRow.linked_number == parent
                    )
                )
            )
        unranked_last = case((TicketRow.rank == 0, 1), else_=0)
        query = query.order_by(unranked_last, TicketRow.rank, TicketRow.number)
        return list(await self._session.scalars(query))
