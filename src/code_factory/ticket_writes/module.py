"""The `ticket_writes` module as the platform sees it.

List it after tickets, git, repositories, stages and undo: it calls their services.
"""

from code_factory.board.service import ColumnLimits
from code_factory.git.service import GitService
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.stages.service import StageService
from code_factory.ticket_writes import tables  # noqa: F401  # puts column_limits on the metadata
from code_factory.ticket_writes.routes import router
from code_factory.ticket_writes.service import TicketWriteService, WritePorts
from code_factory.tickets.service import TicketService
from code_factory.undo.service import UndoService


class ColumnLimitsAdapter:
    """`ColumnLimits`: the limits the owner set on the board's columns."""

    def __init__(self, writes: TicketWriteService) -> None:
        self._writes = writes

    async def column_limits(self) -> dict[str, int]:
        """The limit of each column that has one."""
        return await self._writes.column_limits()


def _provide(services: Services, resources: Resources) -> None:
    ports = WritePorts(
        tickets=services.get(TicketService),
        stages=services.get(StageService),
        git=services.get(GitService),
        repositories=services.get(RepositoryService),
    )
    writes = TicketWriteService(resources.uow, ports, services.get(UndoService))
    services.add(TicketWriteService, writes)
    services.add(ColumnLimits, ColumnLimitsAdapter(writes))


module = Module(name="ticket_writes", provide=_provide, router=router)
