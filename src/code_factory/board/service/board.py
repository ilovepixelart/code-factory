"""The board's reads: the board, the ticket list, one ticket's page, the archive and the views.

Every read is assembled from other modules' services in a fixed number of reads however many
tickets there are, and writes nothing (the views apart). The modules answer separately, so one
answer may combine states a few milliseconds apart; the next poll corrects it.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from code_factory.board.models import ArchiveQuery, OffBoardRow, Tagged
from code_factory.board.rules.archive import RELEASED, archive_rows
from code_factory.board.rules.budget import month_budget
from code_factory.board.rules.columns import board_answer, group_columns
from code_factory.board.rules.etag import body_of, etag_of
from code_factory.board.rules.filters import TicketsFilter, ticket_list_card
from code_factory.board.rules.marks import left_board
from code_factory.board.service.cards import build_cards
from code_factory.board.service.page import PageReader
from code_factory.board.service.sources import BoardSources
from code_factory.board.service.views import ViewBook
from code_factory.board.service.world import World, read_placed, read_tickets, read_world
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.platform.text.paging import Paging
from code_factory.tickets.models import ActivityMarks, Ticket

TALK_PAGE = 100
# The repository a ticket is filed in until a repository is tracked (`code-factory repo track`).
TICKET_TYPES = frozenset({"feature", "bug", "refactor", "upgrade", "hotfix", "docs"})


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BoardService:
    """The reads behind the board, the ticket page, the archive and the repository list."""

    def __init__(
        self,
        sources: BoardSources,
        uow: UnitOfWork,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._sources = sources
        self._clock = clock
        self._views = ViewBook(uow)
        self._page = PageReader(sources)

    async def list_views(self) -> list[dict[str, str]]:
        """The saved views, in the order saved."""
        return await self._views.all()

    async def save_view(self, name: str, query: str) -> None:
        """Save the board's current filters under a name."""
        await self._views.save(name, query)

    async def delete_view(self, name: str) -> None:
        """Delete a saved view."""
        await self._views.delete(name)

    async def repositories(self) -> list[str]:
        """The tracked repositories and those tickets are filed in, in name order.

        None on a new install: the web app then guides the owner to track one first.
        """
        tracked = {r.name for r in await self._sources.repositories.list()}
        tickets = await read_tickets(self._sources)
        return sorted(tracked | {t.repository for t in tickets})

    async def _cards(self, world: World) -> list[dict[str, Any]]:
        return await build_cards(self._sources, world, world.on_board())

    async def board(self) -> Tagged:
        """Every open ticket by column, compactly serialised, with its ETag."""
        world = await read_world(self._sources, self._clock())
        limits = await self._sources.limits.column_limits()
        body = body_of(board_answer(await self._cards(world), limits, world.problems, world.now))
        return Tagged(body=body, etag=etag_of(body))

    async def tickets(self, filters: dict[str, list[str]]) -> dict[str, Any]:
        """The open tickets that match every filter given, by column."""
        wanted = TicketsFilter.from_pairs((k, v) for k, values in filters.items() for v in values)
        world = await read_world(self._sources, self._clock())
        kept = [card for card in await self._cards(world) if wanted.matches(card)]
        columns = group_columns(kept)
        return {
            "columns": {n: [ticket_list_card(c) for c in cards] for n, cards in columns.items()},
            "problems": world.problems,
        }

    async def ticket_card(self, repository: str, ticket_id: str) -> dict[str, Any] | None:
        """The card of a ticket of any state, archived and released too; None when there is none."""
        try:
            found = await self._ticket(repository, ticket_id)
        except NotFoundError:
            return None
        world = await read_world(self._sources, self._clock(), found)
        return (await build_cards(self._sources, world, [found]))[0]

    async def ticket_page(self, repository: str, ticket_id: str) -> dict[str, Any]:
        """One ticket's page; `NotFoundError` for an id that is none or in another repository."""
        ticket = await self._ticket(repository, ticket_id)
        world = await read_world(self._sources, self._clock(), ticket)
        return await self._page.page(world, ticket)

    async def month_budget(self, repository: str) -> dict[str, Any] | None:
        """The repository's spend this UTC month against its monthly budget; None without one."""
        world = await read_world(self._sources, self._clock())
        facts = world.repositories.get(repository)
        if facts is None:
            raise NotFoundError("unknown repository")
        if facts.monthly_budget_usd is None:
            return None
        spent = await self._page.month_spent(repository, world.now)
        return month_budget(spent, facts.monthly_budget_usd, world.now)

    async def evidence_summary(self, ticket_id: str) -> dict[str, Any]:
        """What the ticket proved, for the pull request body."""
        tickets = await read_tickets(self._sources)
        ticket = next((t for t in tickets if t.id == ticket_id), None)
        if ticket is None:
            raise NotFoundError("no such ticket")
        return await self._page.summary(ticket)

    async def template(self, repository: str, kind: str) -> dict[str, str]:
        """The repository's template for a ticket type; empty when it has none or is untracked."""
        try:
            root = await self._sources.repositories.get(repository)
        except NotFoundError:
            if kind not in TICKET_TYPES:
                raise BadRequestError(f"unknown type {kind}") from None
            return {"text": ""}
        return {"text": await self._sources.settings.ticket_template(root, kind)}

    async def archive(self, query: dict[str, str]) -> dict[str, Any]:
        """The tickets off the board, searched, sorted and paged."""
        ask = ArchiveQuery(
            q=query.get("q", ""),
            sort=query.get("sort", ""),
            dir=query.get("dir", ""),
            show=query.get("show", ""),
            paging=Paging.from_query(query.get("page"), query.get("size")),
        )
        tickets, placements = await read_placed(self._sources)
        stage = {
            t.id: placements[t.id].stage if t.id in placements else t.column.value for t in tickets
        }
        off = [t for t in tickets if t.archived or stage[t.id] == RELEASED]
        named = await self._sources.releases.naming(
            [(t.repository, t.id) for t in off if stage[t.id] == RELEASED]
        )
        marks = await self._sources.activity.latest_marks([t.id for t in off])
        rows = [self._off_board(t, stage[t.id], named, marks.get(t.id)) for t in off]
        return archive_rows(rows, ask)

    @staticmethod
    def _off_board(
        ticket: Ticket,
        stage: str,
        named: dict[tuple[str, str], Any],
        marks: ActivityMarks | None,
    ) -> OffBoardRow:
        release = named.get((ticket.repository, ticket.id))
        return OffBoardRow(
            repository=ticket.repository,
            id=ticket.id,
            title=ticket.title,
            type=ticket.type,
            stage=stage,
            archived=ticket.archived,
            priority=ticket.priority,
            assignee=ticket.assignee,
            rank=ticket.rank,
            archived_at=left_board(release.published_at if release else None, marks),
            release=release.version if release else "",
        )

    async def _ticket(self, repository: str, ticket_id: str) -> Ticket:
        try:
            ticket = await self._sources.tickets.get(ticket_id)
        except (BadRequestError, NotFoundError) as error:
            raise NotFoundError("no such ticket") from error
        if ticket.repository != repository:
            raise NotFoundError("no such ticket")
        return ticket
