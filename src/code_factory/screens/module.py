"""The `screens` module as the platform sees it.

List it after tickets, and before inbox, which lists the captures that wait.
"""

from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.screens.cli import shoot_command
from code_factory.screens.routes import router
from code_factory.screens.service import ScreensService
from code_factory.tickets.service import ActivityService, TicketService


def _provide(services: Services, resources: Resources) -> None:
    folder = resources.settings.state_dir / "captures"
    services.add(
        ScreensService,
        ScreensService(services.get(TicketService), services.get(ActivityService), folder),
    )


module = Module(name="screens", provide=_provide, router=router, commands=(shoot_command,))
