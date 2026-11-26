"""The ticket write service: the public API of the module, one use case per method."""

from collections.abc import Callable
from datetime import datetime

from code_factory.platform.db import UnitOfWork
from code_factory.ticket_writes.service.base import (
    KIND,
    ActiveRuns,
    DuplicateQuestion,
    GitPort,
    WritePorts,
)
from code_factory.ticket_writes.service.creating import Creating
from code_factory.ticket_writes.service.editing import Editing
from code_factory.ticket_writes.service.moving import Moving
from code_factory.ticket_writes.service.removing import Removing
from code_factory.ticket_writes.service.reverting import Reverting
from code_factory.tickets.service import utc_now
from code_factory.undo.service import UndoService


class TicketWriteService(Creating, Editing, Moving, Removing, Reverting):
    """Every change the app makes to a ticket card, each in one transaction with its records.

    Registers `tickets.revert` with the undo store when built: one undo service holds one handler
    per kind.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        ports: WritePorts,
        undo: UndoService,
        *,
        clock: Callable[[], datetime] = utc_now,
        write_wait: float = 20.0,
    ) -> None:
        super().__init__(uow, ports, undo, clock=clock, write_wait=write_wait)
        undo.register(KIND, self._revert)


__all__ = [
    "ActiveRuns",
    "DuplicateQuestion",
    "GitPort",
    "TicketWriteService",
    "WritePorts",
]
