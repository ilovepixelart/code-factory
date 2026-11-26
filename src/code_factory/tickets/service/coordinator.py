"""The coordinator's edits of a ticket, and taking them back through the undo store."""

from typing import Any

from code_factory.tickets.models import TicketFields
from code_factory.tickets.service.tickets import TicketService
from code_factory.undo.models import Changed
from code_factory.undo.service import UndoService

UNDO_KIND = "ticket.coordinator_edit"


class CoordinatorService:
    """Edit a ticket as the coordinator, and put its fields back."""

    def __init__(self, tickets: TicketService, undo: UndoService) -> None:
        self._tickets = tickets
        self._undo = undo
        undo.register(UNDO_KIND, self._take_back)

    async def edit(self, ticket: str, fields: TicketFields, *, by: str) -> Changed:
        """Apply an edit of the four fields the coordinator may set; the answer holds an undo token.

        Each changed field is recorded as a `coordinator_edit`. An edit that changes nothing
        writes nothing and offers no undo.
        """
        edited = await self._tickets.update(ticket, fields, by=by, coordinator=True)
        if not edited.changed:
            return Changed(notice=f"Nothing changed on {edited.ticket.id}", undo=None)
        payload = {
            "ticket": edited.ticket.id,
            "edits": {name: {"from": was, "to": now} for name, (was, now) in edited.moved.items()},
        }
        notice = f"Updated {', '.join(edited.changed)} of {edited.ticket.id}"
        return await self._undo.offer(UNDO_KIND, payload, notice)

    async def undo_edit(self, ticket: str, name: str, *, by: str) -> Changed:
        """Put one field back to what the coordinator's latest edit of it replaced.

        Refused (`ConflictError`) once the field changed since, and `NotFoundError` when the
        coordinator never edited it.
        """
        edits = await self._tickets.coordinator_edits(ticket, [name])
        restored = await self._tickets.put_back(ticket, edits, by=by)
        return Changed(notice=f"Put {name} back to {restored[name]}", undo=None)

    async def _take_back(self, payload: dict[str, Any], by: str) -> None:
        edits = {name: (edit["from"], edit["to"]) for name, edit in payload["edits"].items()}
        await self._tickets.put_back(payload["ticket"], edits, by=by)
