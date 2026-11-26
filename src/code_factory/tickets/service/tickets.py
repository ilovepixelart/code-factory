"""Tickets and the facts their column is read from."""

import builtins
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from code_factory.platform.errors import ConflictError, NotFoundError
from code_factory.tickets.models import (
    Edited,
    NewTicket,
    PullRequest,
    Ticket,
    TicketFields,
    TicketFilter,
    TicketRef,
    TicketView,
)
from code_factory.tickets.repository import DocumentRepository, TicketRepository
from code_factory.tickets.rules import (
    MAX_NUMBER,
    check_branch,
    check_coordinator_fields,
    clean_fields,
    field_text,
    ticket_id,
    ticket_number,
)
from code_factory.tickets.service.activity import to_activity
from code_factory.tickets.service.common import not_found, to_ticket
from code_factory.tickets.service.documents import document_index
from code_factory.tickets.service.fieldwrite import insert_ticket, read_ticket, write_fields
from code_factory.tickets.service.lookups import TicketLookups, to_ref
from code_factory.tickets.tables import TicketRow

RECENT_RECORDS = 5
Change = Callable[[TicketRepository, TicketRow], Awaitable[None]]
Edit = Callable[[TicketRow], None]


class TicketService(TicketLookups):
    """Tickets and their facts."""

    async def create(self, new: NewTicket, *, by: str) -> Ticket:
        """Create a ticket under the next number of the sequence; records `created`.

        A `source` is held by one ticket per repository (`ConflictError` for a second).
        """
        return await self._file(new, by, {})

    async def create_scratch(self, new: NewTicket, *, by: str) -> Ticket:
        """File a ticket that is off the board from the start, for a run that needs one to work on.

        Its source is `scratch:<token>`. It is on no board, list or count, and `delete_scratch`
        removes it with its history.
        """
        scratch = new.model_copy(update={"source": f"scratch:{uuid4().hex}"})
        return await self._file(scratch, by, {"archived": True, "scratch": True})

    async def delete_scratch(self, ticket: str) -> None:
        """Delete a scratch ticket with its history; `ConflictError` for any other ticket."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            row = await tickets.find(number, for_update=True)
            if row is None:
                raise not_found(number)
            if not row.scratch:
                raise ConflictError(f"{ticket_id(number)} is not a scratch ticket")
            await tickets.delete_with_history(number)

    async def ref_of(self, ticket: str) -> TicketRef:
        """The reference of the ticket `CF-<n>`; `NotFoundError` when there is none."""
        return to_ref(await self.get(ticket))

    async def locate(self, repository: str, ticket: str) -> TicketRef:
        """The reference of the ticket when it belongs to `repository`, else `NotFoundError`."""
        found = await self.ref_of(ticket)
        if found.repository != repository:
            raise NotFoundError("no such ticket")
        return found

    async def live_refs(self) -> builtins.list[TicketRef]:
        """The reference of every ticket not archived, in board order."""
        return [to_ref(ticket) for ticket in await self.list()]

    async def _file(self, new: NewTicket, by: str, extra: dict[str, Any]) -> Ticket:
        now = self._clock()
        async with self._uow() as session:
            tickets = TicketRepository(session)
            row = await insert_ticket(tickets, new, now, extra)
            await tickets.append_activity(row.number, (now, "created", by), {"type": row.type})
            return await read_ticket(tickets, row)

    async def get(self, ticket: str) -> Ticket:
        """The ticket `CF-<n>`; `NotFoundError` when there is none."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            row = await tickets.find(number)
            if row is None:
                raise not_found(number)
            return await read_ticket(tickets, row)

    async def repository_of(self, ticket: str) -> str | None:
        """The repository the ticket belongs to, `None` when there is no such ticket."""
        number = ticket_number(ticket)
        if number > MAX_NUMBER:
            return None
        async with self._uow() as session:
            row = await TicketRepository(session).find(number)
            return None if row is None else row.repository

    async def get_view(self, ticket: str) -> TicketView:
        """The ticket, its document index (no text) and its five latest records, newest first."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            row = await tickets.find(number)
            if row is None:
                raise not_found(number)
            found = await read_ticket(tickets, row)
            documents = await DocumentRepository(session).of(number)
            recent = await tickets.activity_of(number, None, (RECENT_RECORDS, None, True))
        return TicketView(
            ticket=found,
            documents=document_index(documents),
            recent_activity=[to_activity(record) for record in recent],
        )

    async def list(self, where: TicketFilter | None = None) -> builtins.list[Ticket]:
        """The tickets `where` selects (by default those not archived), in board order."""
        where = where or TicketFilter()
        parent = ticket_number(where.parent) if where.parent is not None else None
        wanted = None if where.ids is None else [ticket_number(i) for i in where.ids]
        if wanted == []:
            return []
        async with self._uow() as session:
            tickets = TicketRepository(session)
            rows = await tickets.select(where, parent, wanted)
            numbers = [row.number for row in rows]
            links = await tickets.links_of(numbers)
            pulls = await tickets.pull_requests_of(numbers)
        found = [to_ticket(row, links[row.number], pulls.get(row.number)) for row in rows]
        return [t for t in found if where.column is None or t.column is where.column]

    async def linking_to(self, ticket: str) -> builtins.list[str]:
        """IDs of tickets that name this ticket as their parent or blocker."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            return [ticket_id(n) for n in await TicketRepository(session).linking_to(number)]

    async def update(
        self, ticket: str, fields: TicketFields, *, by: str, coordinator: bool = False
    ) -> Edited:
        """Change the given fields; answers the ticket and the names of the fields that changed.

        A change is recorded as an `edited` activity naming the fields; an edit that changes
        nothing writes nothing.

        With `coordinator`, only the fields the coordinator may set are accepted and each change
        is also recorded as a `coordinator_edit` (`name`, `from`, `to`, each as the field holds it).
        """
        number = ticket_number(ticket)
        cleaned = clean_fields(fields)
        if coordinator:
            check_coordinator_fields(cleaned)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            row = await tickets.find(number, for_update=True)
            if row is None:
                raise not_found(number)
            return await self._edit(tickets, row, cleaned, (by, coordinator))

    async def coordinator_edits(
        self, ticket: str, names: builtins.list[str]
    ) -> dict[str, tuple[Any, Any]]:
        """Each field's latest `coordinator_edit` as `(from, to)`; `NotFoundError` if none."""
        check_coordinator_fields(names)
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number) is None:
                raise not_found(number)
            edits = {}
            for name in names:
                edit = await tickets.latest_coordinator_edit(number, name)
                if edit is None:
                    msg = f"the coordinator made no edit of {name} on {ticket_id(number)}"
                    raise NotFoundError(msg)
                edits[name] = (edit.data["from"], edit.data["to"])
            return edits

    async def put_back(
        self, ticket: str, edits: dict[str, tuple[Any, Any]], *, by: str
    ) -> dict[str, str]:
        """Set each coordinator field from `to` back to `from`, as the actor's own edit.

        Every field is checked against `to` first and one that holds anything else now refuses
        them all (`ConflictError`). Answers each field with the value it was set to, as text.
        """
        check_coordinator_fields(edits)
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            row = await tickets.find(number, for_update=True)
            if row is None:
                raise not_found(number)
            current = await read_ticket(tickets, row)
            for name, (_, left) in edits.items():
                now = getattr(current, name)
                if now != left:
                    msg = (
                        f"{name} changed since: it is {field_text(now)} now, not "
                        f"{field_text(left)} as the coordinator left it"
                    )
                    raise ConflictError(msg)
            cleaned = clean_fields(TicketFields(**{name: edit[0] for name, edit in edits.items()}))
            await self._edit(tickets, row, cleaned, (by, False))
            return {name: field_text(edit[0]) for name, edit in edits.items()}

    async def _edit(
        self,
        tickets: TicketRepository,
        row: TicketRow,
        cleaned: dict[str, Any],
        actor: tuple[str, bool],
    ) -> Edited:
        by, coordinator = actor
        now = self._clock()
        current, after, changed = await write_fields(tickets, row, cleaned, now)
        if not changed:
            return Edited(ticket=current, changed=[])
        await tickets.append_activity(row.number, (now, "edited", by), {"fields": changed})
        moved = {name: (getattr(current, name), getattr(after, name)) for name in changed}
        if coordinator:
            for name, (was, holds) in moved.items():
                record = {"name": name, "from": was, "to": holds}
                await tickets.append_activity(row.number, (now, "coordinator_edit", by), record)
        return Edited(ticket=after, changed=changed, moved=moved if coordinator else {})

    async def set_branch(self, ticket: str, branch: str, *, by: str) -> Ticket:
        """Give the ticket its branch (a plain branch name); it is in Build from then on."""
        name = check_branch(branch)

        def edit(row: TicketRow) -> None:
            row.branch = name

        return await self._change(ticket, by, edit=edit)

    async def clear_branch(self, ticket: str, *, by: str) -> Ticket:
        """Take the ticket's branch away."""

        def edit(row: TicketRow) -> None:
            row.branch = ""

        return await self._change(ticket, by, edit=edit)

    async def set_pull_request(self, ticket: str, pull: PullRequest, *, by: str) -> Ticket:
        """Record the ticket's pull request and its state, replacing the one it had."""
        now = self._clock()

        async def change(tickets: TicketRepository, row: TicketRow) -> None:
            await tickets.put_pull_request(row.number, pull, now)

        return await self._change(ticket, by, change=change)

    async def clear_pull_request(self, ticket: str, *, by: str) -> Ticket:
        """Forget the ticket's pull request."""

        async def change(tickets: TicketRepository, row: TicketRow) -> None:
            await tickets.remove_pull_request(row.number)

        return await self._change(ticket, by, change=change)

    async def set_merged(self, ticket: str, merged: bool, *, by: str) -> Ticket:
        """Record whether the ticket's work is merged, with or without a pull request."""

        def edit(row: TicketRow) -> None:
            row.merged = merged

        return await self._change(ticket, by, edit=edit)

    async def archive(self, ticket: str, *, by: str) -> Ticket:
        """Take the ticket off the board; records `archived`."""

        def edit(row: TicketRow) -> None:
            row.archived = True

        return await self._change(ticket, by, edit=edit, record="archived")

    async def unarchive(self, ticket: str, *, by: str) -> Ticket:
        """Put the ticket back on the board; records `restored`."""

        def edit(row: TicketRow) -> None:
            row.archived = False

        return await self._change(ticket, by, edit=edit, record="restored")

    async def _change(
        self,
        ticket: str,
        by: str,
        *,
        edit: Edit | None = None,
        change: Change | None = None,
        record: str | None = None,
    ) -> Ticket:
        """Apply `edit` to the locked ticket's row, or `change` through its repository.

        Records `record` and a column move if it moved; a change that leaves the ticket as it was
        writes nothing.
        """
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            row = await tickets.find(number, for_update=True)
            if row is None:
                raise not_found(number)
            before = await read_ticket(tickets, row)
            if edit is not None:
                edit(row)
            if change is not None:
                await change(tickets, row)
            await tickets.flush()
            after = await read_ticket(tickets, row)
            if after == before:
                return before
            now = self._clock()
            row.updated_at = now
            if record is not None:
                await tickets.append_activity(number, (now, record, by), {})
            if after.column is not before.column:
                moved = {"from": before.column.value, "to": after.column.value}
                await tickets.append_activity(number, (now, "stage", by), moved)
            return await read_ticket(tickets, row)
