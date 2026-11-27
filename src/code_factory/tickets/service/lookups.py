"""What other modules ask of the ticket service: references, lookups, flow facts, scratch."""

import builtins
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

from code_factory.platform.db import UnitOfWork
from code_factory.tickets.models import (
    Activity,
    Column,
    Diagnosis,
    DocHit,
    DocumentName,
    NewActivity,
    NoteKind,
    StageMove,
    Ticket,
    TicketAddress,
    TicketCore,
    TicketFlow,
    TicketRef,
)
from code_factory.tickets.repository import TicketRepository
from code_factory.tickets.rules import MAX_NUMBER, ticket_id, ticket_number
from code_factory.tickets.service.activity import ActivityService
from code_factory.tickets.service.common import to_ticket, utc_now
from code_factory.tickets.service.fieldwrite import read_ticket
from code_factory.tickets.service.unit import TicketUnit


def to_ref(ticket: Ticket) -> TicketRef:
    """A ticket's reference."""
    return TicketRef(
        id=ticket.id,
        repository=ticket.repository,
        title=ticket.title,
        column=ticket.column,
        labels=ticket.labels,
        rank=ticket.rank,
        branch=ticket.branch,
    )


class TicketLookups:
    """Reads and small writes the other modules call on the ticket service."""

    def __init__(self, uow: UnitOfWork, clock: Callable[[], datetime] = utc_now) -> None:
        self._uow = uow
        self._clock = clock

    @asynccontextmanager
    async def unit(
        self, repositories: builtins.list[str], *, wait: float
    ) -> AsyncGenerator[TicketUnit]:
        """One transaction that holds a lock on each named repository, taken in name order.

        A lock not got within `wait` seconds is `UnavailableError`. The transaction commits when
        the block ends and is rolled back when it raises.
        """
        async with self._uow() as session:
            tickets = TicketRepository(session)
            await tickets.lock_repositories(repositories, wait)
            yield TicketUnit(tickets, self._clock)

    async def get_core(self, address: TicketAddress) -> TicketCore | None:
        """The live ticket the address names, or `None`."""
        async with self._uow() as session:
            tickets = TicketRepository(session)
            number = ticket_number(address.id)
            row = await tickets.find(number) if number <= MAX_NUMBER else None
            if row is None or row.repository != address.repository:
                return None
            ticket = await read_ticket(tickets, row)
            return TicketCore(**ticket.model_dump(), trashed=False)

    async def list_repositories(self) -> builtins.list[str]:
        """The repositories that hold a ticket on the board, by name."""
        async with self._uow() as session:
            return await TicketRepository(session).repositories()

    async def list_diagnoses(self) -> builtins.list[Diagnosis]:
        """Every diagnosis posted on a ticket, newest first."""
        async with self._uow() as session:
            rows = await TicketRepository(session).diagnoses()
        return [
            Diagnosis(
                ticket_id=ticket_id(row.ticket_number),
                author=row.by,
                text=str(row.data.get("text", "")),
                at=row.at,
            )
            for row in rows
        ]

    async def find_by_source(self, repository: str, source: str) -> Ticket | None:
        """The ticket of `repository` filed from `source`, or `None`."""
        async with self._uow() as session:
            tickets = TicketRepository(session)
            row = await tickets.find_by_source(repository, source)
            if row is None:
                return None
            links = await tickets.links_of([row.number])
            pulls = await tickets.pull_requests_of([row.number])
            return to_ticket(row, links[row.number], pulls.get(row.number))

    async def existing_sources(self, repository: str) -> frozenset[str]:
        """The sources the repository's tickets were filed from."""
        async with self._uow() as session:
            return frozenset(await TicketRepository(session).sources_of(repository))

    async def find_by_branch(self, repository: str, branch: str) -> Ticket | None:
        """The ticket of `repository` that holds `branch`, or `None`."""
        async with self._uow() as session:
            tickets = TicketRepository(session)
            row = await tickets.find_by_branch(repository, branch)
            if row is None:
                return None
            links = await tickets.links_of([row.number])
            pulls = await tickets.pull_requests_of([row.number])
            return to_ticket(row, links[row.number], pulls.get(row.number))

    async def merged(self, repository: str, ids: builtins.list[str]) -> frozenset[str]:
        """The ids among `ids`, tickets of `repository`, whose work is merged."""
        numbers = [ticket_number(i) for i in ids]
        if not numbers:
            return frozenset()
        async with self._uow() as session:
            found = await TicketRepository(session).merged_among(repository, numbers)
        return frozenset(ticket_id(n) for n in found)

    async def titles(self, ids: builtins.list[str]) -> dict[str, str]:
        """Titles of the named visible tickets in one read."""
        if not ids:
            return {}
        async with self._uow() as session:
            found = await TicketRepository(session).titles([ticket_number(i) for i in ids])
        return {ticket_id(number): title for number, title in found.items()}

    async def open_titles(self, repository: str) -> builtins.list[tuple[str, str]]:
        """`(id, title)` of each ticket of the repository neither archived nor merged."""
        async with self._uow() as session:
            rows = await TicketRepository(session).open_titles(repository)
        return [(ticket_id(number), title) for number, title in rows]

    async def search_documents(
        self, repository: str, words: builtins.list[str], limit: int
    ) -> builtins.list[DocHit]:
        """Up to `limit` documents of the repository's tickets holding every word, any case."""
        async with self._uow() as session:
            rows = await TicketRepository(session).search_documents(repository, words, limit)
        return [
            DocHit(ticket_id=ticket_id(r.ticket_number), name=DocumentName(r.name), text=r.body)
            for r in rows
        ]

    async def flow_facts(
        self,
        repository: str,
        ids: builtins.list[str] | None = None,
        stages: builtins.list[Column] | None = None,
    ) -> builtins.list[TicketFlow]:
        """What the flow measures read of the repository's tickets, archived ones included.

        `ids` and `stages` narrow the answer; a move is a `stage` record, oldest first.
        """
        wanted = None if ids is None else [ticket_number(i) for i in ids]
        async with self._uow() as session:
            tickets = TicketRepository(session)
            rows = await tickets.flow_rows(repository, wanted)
            numbers = [row.number for row in rows]
            links = await tickets.links_of(numbers)
            pulls = await tickets.pull_requests_of(numbers)
            records = await tickets.moves_of(numbers) if numbers else []
        moves: dict[int, builtins.list[StageMove]] = {n: [] for n in numbers}
        columns = {column.value for column in Column}
        for record in records:
            if record.data.get("to") in columns:
                moves[record.ticket_number].append(
                    StageMove(at=record.at, to=Column(record.data["to"]))
                )
        flows = []
        for row in rows:
            ticket = to_ticket(row, links[row.number], pulls.get(row.number))
            if stages is not None and ticket.column not in stages:
                continue
            flows.append(
                TicketFlow(
                    id=ticket.id,
                    title=ticket.title,
                    stage=ticket.column,
                    archived=ticket.archived,
                    branch=ticket.branch,
                    created_at=ticket.created_at,
                    caused_by=ticket.caused_by,
                    moves=moves[row.number],
                )
            )
        return flows

    async def record_activity(
        self,
        ticket: str,
        kind: str,
        data: dict[str, object],
        *,
        by: str,
        at: datetime | None = None,
    ) -> Activity:
        """Append a record of `kind` to the ticket's history."""
        record = NewActivity(kind=kind, data=data, at=at)
        return await ActivityService(self._uow, self._clock).append(ticket, record, by=by)

    async def record_note(self, ticket: str, text: str, kind: NoteKind, *, by: str) -> Activity:
        """A note, or a diagnosis, on the ticket's history under the actor's name."""
        return await ActivityService(self._uow, self._clock).record_note(ticket, text, kind, by=by)

    async def count_authored(self, by: str, kind: str) -> int:
        """How many records of `kind` the actor wrote on every ticket."""
        return await ActivityService(self._uow, self._clock).count_authored(by, kind)
