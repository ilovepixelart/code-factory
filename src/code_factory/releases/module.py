"""The `releases` module as the platform sees it."""

from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.releases import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.releases.cli import release_command
from code_factory.releases.service import ReleaseService
from code_factory.tickets.service import TicketService


def _provide(services: Services, resources: Resources) -> None:
    services.add(ReleaseService, ReleaseService(resources.uow, services.get(TicketService)))


module = Module(name="releases", provide=_provide, commands=(release_command,))
