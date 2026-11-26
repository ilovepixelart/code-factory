"""Deleting a ticket and the column limits."""

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.ticket_writes.models import STAGES
from code_factory.ticket_writes.repository import ColumnLimitRepository
from code_factory.ticket_writes.rules import limit_value
from code_factory.ticket_writes.service.base import NO_TICKET, WriteBase
from code_factory.tickets.models import TicketAddress
from code_factory.undo.models import Changed

RUNNING = "an agent is running on this ticket; stop it first"


class Removing(WriteBase):
    """Delete a ticket (soft, undoable) and set the columns' limits."""

    async def delete(self, ref: TicketAddress, by: str) -> Changed:  # noqa: ARG002  # the actor of a record the delete does not write
        """Hide the ticket from every read; refused while an agent runs on it."""
        found = await self._core(ref)
        if self._active_runs is not None and await self._active_runs(ref):
            raise ConflictError(RUNNING)
        async with self._unit([ref.repository]) as unit:
            if not await unit.trash(ref):
                raise NotFoundError(NO_TICKET)
        back = {"op": "restore", "repository": ref.repository, "id": found.id}
        return await self._offer([back], f"Deleted {found.id}")

    async def set_column_limit(self, stage: str, raw: object, by: str) -> Changed:  # noqa: ARG002
        """Limit the open tickets of a column; `None` clears the limit."""
        if stage not in STAGES:
            raise BadRequestError(f"unknown stage {stage}")
        limit = limit_value(raw)
        if isinstance(limit, str):
            raise BadRequestError(limit)
        async with self._uow() as session:
            await session.connection()
            now = self._clock()
            limits = ColumnLimitRepository(session)
            await (limits.clear(stage) if limit is None else limits.put(stage, limit, now))
        return Changed(notice="", undo=None)

    async def column_limits(self) -> dict[str, int]:
        """Every limited column and its limit."""
        async with self._uow() as session:
            return await ColumnLimitRepository(session).all()
