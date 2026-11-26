"""The unit of work other modules write tickets through: one transaction, locked per repository."""

from collections.abc import Callable
from datetime import datetime

from code_factory.platform.errors import BadRequestError
from code_factory.tickets.models import (
    LinkGraph,
    NewTicket,
    TicketAddress,
    TicketCore,
    TicketFields,
)
from code_factory.tickets.repository import TicketRepository
from code_factory.tickets.rules import (
    MAX_NUMBER,
    check_kind,
    clean_fields,
    ticket_id,
    ticket_number,
)
from code_factory.tickets.service.common import not_found
from code_factory.tickets.service.fieldwrite import insert_ticket, read_ticket, write_fields
from code_factory.tickets.tables import TicketRow


class TicketUnit:
    """Reads and writes of tickets in one transaction; nothing is kept when its block raises.

    A ticket is named by `TicketAddress`: one of another repository is not found. A trashed
    ticket is hidden from every read but `get_deleted`. Writes record no activity of their own
    except `record`: the caller says what its use case did.
    """

    def __init__(self, tickets: TicketRepository, clock: Callable[[], datetime]) -> None:
        self._tickets = tickets
        self._clock = clock

    async def _row(self, address: TicketAddress, *, trashed: bool = False) -> TicketRow | None:
        number = ticket_number(address.id)
        if number > MAX_NUMBER:
            return None
        row = await self._tickets.find(number, for_update=True, trashed=trashed)
        return row if row is not None and row.repository == address.repository else None

    async def _locked(self, address: TicketAddress) -> TicketRow:
        row = await self._row(address)
        if row is None:
            raise not_found(ticket_number(address.id))
        return row

    async def _core(self, row: TicketRow) -> TicketCore:
        ticket = await read_ticket(self._tickets, row)
        return TicketCore(**ticket.model_dump(), trashed=row.trashed)

    async def get(self, address: TicketAddress) -> TicketCore | None:
        """The live ticket, or `None`."""
        row = await self._row(address)
        return None if row is None else await self._core(row)

    async def get_deleted(self, address: TicketAddress) -> TicketCore | None:
        """The trashed ticket, or `None`."""
        row = await self._row(address, trashed=True)
        return None if row is None else await self._core(row)

    async def link_graph(self, repository: str) -> LinkGraph:
        """The live tickets of the repository and each one's parent, in one read."""
        rows = await self._tickets.link_graph(repository)
        return LinkGraph(
            ids=[ticket_id(number) for number, _ in rows],
            parent_of={ticket_id(n): ticket_id(parent) for n, parent in rows if parent is not None},
        )

    async def insert(self, new: NewTicket) -> TicketAddress:
        """File the ticket under the next number; it has no history until `record` writes some."""
        row = await insert_ticket(self._tickets, new, self._clock())
        return TicketAddress(repository=row.repository, id=ticket_id(row.number))

    async def save_fields(self, address: TicketAddress, fields: TicketFields) -> list[str]:
        """Set the given fields; answers the names that changed (none: nothing is written)."""
        row = await self._locked(address)
        _, _, changed = await write_fields(self._tickets, row, clean_fields(fields), self._clock())
        return changed

    async def set_archived(self, address: TicketAddress, *, archived: bool) -> bool:
        """Take the ticket off the board or put it back; `False` when it already was so."""
        row = await self._locked(address)
        return await self._set(row, "archived", archived)

    async def set_branch(self, address: TicketAddress, branch: str) -> bool:
        """Give the ticket its branch (empty takes it away); `False` when it already held it.

        The name is the caller's to have checked: this writes what it is given.
        """
        row = await self._locked(address)
        return await self._set(row, "branch", branch)

    async def _set(self, row: TicketRow, name: str, value: bool | str) -> bool:
        if getattr(row, name) == value:
            return False
        setattr(row, name, value)
        row.updated_at = self._clock()
        await self._tickets.flush()
        return True

    async def record(
        self, address: TicketAddress, kind: str, data: dict[str, object], *, by: str
    ) -> None:
        """Append a record to the ticket's history (not one only the review writes)."""
        row = await self._locked(address)
        await self._tickets.append_activity(row.number, (self._clock(), check_kind(kind), by), data)

    async def set_ranks(self, repository: str, ranks: dict[str, int]) -> None:
        """Set each named ticket's rank; an id that is no ticket of the repository is skipped."""
        numbers: dict[int, int] = {}
        for ticket, rank in ranks.items():
            try:
                number = ticket_number(ticket)
            except BadRequestError:
                continue
            if number <= MAX_NUMBER:
                numbers[number] = rank
        await self._tickets.set_ranks(repository, numbers)

    async def trash(self, address: TicketAddress) -> bool:
        """Delete the ticket from every read; `False` when it was not there to delete."""
        return await self._move(await self._row(address), trashed=True)

    async def restore(self, address: TicketAddress) -> bool:
        """Bring a trashed ticket back; `False` when it was not trashed."""
        return await self._move(await self._row(address, trashed=True), trashed=False)

    async def _move(self, row: TicketRow | None, *, trashed: bool) -> bool:
        if row is None:
            return False
        row.trashed = trashed
        await self._tickets.flush()
        return True
