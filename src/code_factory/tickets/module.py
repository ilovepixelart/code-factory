"""The `tickets` module as the platform sees it."""

from code_factory.platform.mcp.scope import TicketRepositories
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.tickets import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.tickets.routes import router
from code_factory.tickets.service import (
    ActivityService,
    CoordinatorService,
    DocumentService,
    QaHoldouts,
    ReviewService,
    TicketService,
)
from code_factory.tickets.tools import register_tools
from code_factory.undo.service import UndoService


def _provide(services: Services, resources: Resources) -> None:
    tickets = TicketService(resources.uow)
    services.add(TicketService, tickets)
    services.add(TicketRepositories, tickets)
    services.add(CoordinatorService, CoordinatorService(tickets, services.get(UndoService)))
    services.add(ActivityService, ActivityService(resources.uow))
    services.add(DocumentService, DocumentService(resources.uow))
    services.add(QaHoldouts, QaHoldouts(resources.settings.state_dir))
    services.add(ReviewService, ReviewService(resources.uow))


module = Module(name="tickets", provide=_provide, router=router, register_tools=register_tools)
